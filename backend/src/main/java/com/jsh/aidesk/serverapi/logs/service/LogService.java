package com.jsh.aidesk.serverapi.logs.service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.logs.mapper.ActionLogMapper;
import com.jsh.aidesk.serverapi.logs.vo.ActionLogCreateRqVo;
import com.jsh.aidesk.serverapi.logs.vo.ActionLogVo;
import com.jsh.aidesk.serverapi.logs.vo.LogFeedItemRsVo;
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;
import com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 로그 페이지 백엔드 — 메시지(A: 휴리스틱 분류) + 액션(B: PostToolUse 훅 기록) 통합 피드.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class LogService {

    private static final int DEFAULT_LIMIT = 100;
    private static final int MAX_LIMIT = 500;
    /** (me) 에이전트는 사용자 본인의 dev Claude 세션 — 로그 피드에서 제외. tmux_session 접두로 식별. */
    private static final String ME_TMUX_PREFIX = "aidesk-self-";

    private final ActionLogMapper actionLogMapper;
    private final MessageMapper messageMapper;
    private final AgentMapper agentMapper;

    /**
     * Helper 의 PostToolUse 훅이 호출. cwd 가 등록된 AI Desk 워커 에이전트의 workspace_dir
     * 와 일치하지 않으면 무시 — 사용자 본인의 dev Claude 또는 AI Desk 외부 Claude 의 액션을
     * 로그에서 배제. (me) 에이전트의 액션도 사용자 본인 활동이라 제외.
     *
     * @return 저장된 logId 또는 null (필터링 됨)
     */
    @Transactional
    public String recordAction(ActionLogCreateRqVo req) {
        String cwd = blankToNull(req.getCwd());
        if (cwd == null) return null;
        AgentVo agent = agentMapper.selectByWorkspaceDir(cwd);
        if (agent == null) return null;
        if (agent.getTmuxSession() != null && agent.getTmuxSession().startsWith(ME_TMUX_PREFIX)) {
            return null; // (me) — 사용자 본인 활동
        }
        ActionLogVo entity = new ActionLogVo();
        entity.setLogId(UUID.randomUUID().toString());
        entity.setAgentId(agent.getAgentId());
        entity.setAgentName(agent.getAgentName());
        entity.setSessionId(blankToNull(req.getSessionId()));
        entity.setTool(req.getTool());
        entity.setCategory(req.getCategory());
        entity.setTarget(blankToNull(req.getTarget()));
        entity.setSummary(blankToNull(req.getSummary()));
        actionLogMapper.insert(entity);
        return entity.getLogId();
    }

    /**
     * 통합 피드 — 메시지 + 액션을 같은 카테고리 필터로 받아 시간 역순 머지.
     *
     * @param category null|"" 이면 전체, 그 외엔 정확히 일치하는 항목만
     * @param limit    상한 (기본 100, 최대 500)
     */
    @Transactional(readOnly = true)
    public List<LogFeedItemRsVo> getFeed(String category, Integer limit) {
        int cap = (limit == null || limit <= 0) ? DEFAULT_LIMIT : Math.min(limit, MAX_LIMIT);
        String cat = (category == null || category.isBlank()) ? null : category;

        List<LogFeedItemRsVo> all = new ArrayList<>();

        // 1) 메시지 — aidesk-channel 의 모든 대화. liki(me) 도 AI 인스턴스라 포함
        //    (사용자가 워커 터미널에 직접 입력한 건 채널을 안 거치므로 애초에 row 가 없음).
        //    status='failed' 는 pre-flight 실패 등으로 전달 못한 메시지 → 카테고리 'error' 로 강제.
        List<MessageItemRsVo> msgs = messageMapper.selectAudit(null, null, null, null, cap);
        for (MessageItemRsVo m : msgs) {
            String c = "failed".equals(m.getStatus()) ? "error" : MessageClassifier.classify(m.getContent());
            if (cat != null && !cat.equals(c)) continue;
            LogFeedItemRsVo item = new LogFeedItemRsVo();
            item.setType("message");
            item.setCreatedAt(m.getCreatedAt() == null ? "" : m.getCreatedAt().toString());
            item.setCategory(c);
            item.setAgentId(m.getFromAgentId());
            item.setAgentName(m.getFromAgentName());
            item.setMessageId(m.getMessageId());
            item.setToAgentId(m.getToAgentId());
            item.setToAgentName(m.getToAgentName());
            item.setContent(m.getContent());
            item.setMessageStatus(m.getStatus());
            item.setErrorReason(m.getErrorReason());
            all.add(item);
        }

        // 2) 액션 — DB 에서 카테고리 필터로 바로
        List<ActionLogVo> actions = actionLogMapper.selectFeed(cat, cap);
        for (ActionLogVo a : actions) {
            LogFeedItemRsVo item = new LogFeedItemRsVo();
            item.setType("action");
            item.setCreatedAt(a.getCreatedAt() == null
                    ? ""
                    : a.getCreatedAt().withOffsetSameInstant(ZoneOffset.UTC).toString());
            item.setCategory(a.getCategory());
            item.setAgentId(a.getAgentId());
            item.setAgentName(a.getAgentName());
            item.setLogId(a.getLogId());
            item.setTool(a.getTool());
            item.setTarget(a.getTarget());
            item.setSummary(a.getSummary());
            item.setSessionId(a.getSessionId());
            all.add(item);
        }

        // 3) 시간 역순 정렬 + cap
        all.sort(Comparator.comparing(LogFeedItemRsVo::getCreatedAt,
                Comparator.nullsLast(Comparator.reverseOrder())));
        if (all.size() > cap) {
            return all.subList(0, cap);
        }
        return all;
    }

    private static String blankToNull(String s) {
        return s == null || s.isBlank() ? null : s;
    }

    /** 사용처 없음 — Java 17+ 모듈 분리 시 외부 호출이 발생할 수 있어 남겨둠. */
    @SuppressWarnings("unused")
    private static OffsetDateTime now() {
        return OffsetDateTime.now(ZoneOffset.UTC);
    }
}
