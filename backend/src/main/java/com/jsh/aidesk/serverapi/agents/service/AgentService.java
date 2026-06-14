package com.jsh.aidesk.serverapi.agents.service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.extern.slf4j.Slf4j;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentCreateRqVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentItemRsVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentListRsVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentSummaryRsVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.common.jwt.AuthContext;
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;
import com.jsh.aidesk.serverapi.messages.websocket.MessageWebSocketBroker;

import lombok.RequiredArgsConstructor;

/**
 * 에이전트 도메인의 CRUD + 요약. macOS-종속 작업은 전부 desktop-agent (Python Helper) 가
 * 담당한다 — 백엔드 컨테이너에서 실행돼도 동작에 변화 없음.
 *
 * delete() 호출 전에 프론트가 헬퍼의 `POST /api/cleanup-agent` 로 tmux 세션과 Terminal
 * 윈도우를 먼저 정리하므로, 본 서비스의 delete() 는 DB 작업만 수행한다.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AgentService {

    private static final Map<String, String> MODEL_FULLNAMES = Map.of(
            "claude", "claude-opus-4-7",
            "codex",  "codex",
            "hermes", "hermes"
    );

    private final AgentMapper agentMapper;
    private final MessageMapper messageMapper;
    private final MessageWebSocketBroker wsBroker;

    @Transactional(readOnly = true)
    public AgentListRsVo getList(String status) {
        return getList(status, null);
    }

    /**
     * @param callerAgentId aidesk-channel mcp 가 호출 시 자기 self_agent_id 동봉. 인증된 호출에선 null.
     *                      caller 의 owner 로 user context 추정 + type 결정 (channel/channel_backend.md §4).
     */
    @Transactional(readOnly = true)
    public AgentListRsVo getList(String status, String callerAgentId) {
        Long me = AuthContext.currentUserOrNull() != null
                ? AuthContext.currentAccountSn()
                : null;

        AgentVo caller = null;
        if (callerAgentId != null && !callerAgentId.isBlank()) {
            caller = agentMapper.selectByIdAnyOwner(callerAgentId);
            // 비인증 호출에서 caller 로 user 추정.
            if (me == null && caller != null) {
                me = caller.getOwnerAccountSn();
            }
        }

        List<AgentVo> rows;
        if (me == null) {
            // 비인증 + caller 모름 — mcp ensureAgentId 의 fallback cwd 매칭용. 전체 list.
            rows = agentMapper.selectAllForSystem();
        } else if (caller != null) {
            // mcp 의 list_agents 호출 — caller 의 channel 기준 권한 필터.
            // Channel A (internal): 같은 user 안 + 본인 (me) 만
            // Channel B (external): 본인 (me) + 사내 동료 + 다른 user external 까지 (cross-user 허용)
            // 브릿지 (me/human): 양쪽 채널 다 보임
            final AgentVo callerForFilter = caller;
            final String callerCh = com.jsh.aidesk.serverapi.messages.service.MessageService.channelOf(caller);
            rows = agentMapper.selectAllForSystem().stream()
                .filter(a -> com.jsh.aidesk.serverapi.messages.service.MessageService.canCommunicate(
                        callerForFilter, a, callerCh,
                        com.jsh.aidesk.serverapi.messages.service.MessageService.channelOf(a)))
                .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
        } else {
            // dashboard 의 cookie 인증 호출 — 본인 user 의 agent 만. frontend 가 type 별 분류.
            rows = new ArrayList<>(agentMapper.selectList(me, status));
        }

        final AgentVo callerFinal = caller;
        final Long meFinal = me;
        List<AgentItemRsVo> list = rows.stream()
                .map(v -> toItem(v, callerFinal, meFinal))
                .toList();

        AgentListRsVo rs = new AgentListRsVo();
        rs.setList(list);
        // summary 는 본인 user 의 통계 — 비인증/caller 미상이면 0.
        rs.setSummary(me == null ? new AgentSummaryRsVo() : buildSummary(me));
        return rs;
    }

    /** channel/channel_backend.md §4 의 type 결정. */
    private static String resolveType(AgentVo agent, AgentVo caller, Long viewerAccountSn) {
        if (caller != null && agent.getAgentId().equals(caller.getAgentId())) {
            return "self";
        }
        // Phase 2 — 외부 AI (mcp 만 동작, helper 환경 아님). 사내 동료 섹션에 표시.
        if ("external".equalsIgnoreCase(agent.getAgentType())) {
            return "external";
        }
        if ("human".equalsIgnoreCase(agent.getModel())) {
            return "human";
        }
        boolean isMe = agent.getTmuxSession() != null
                && agent.getTmuxSession().startsWith("aidesk-self-");
        if (isMe) {
            // viewer 와 같은 user 의 (me) 면 "me", 다르면 사내 동료 "colleague".
            if (viewerAccountSn != null
                    && viewerAccountSn.equals(agent.getOwnerAccountSn())) {
                return "me";
            }
            return "colleague";
        }
        return "internal";
    }

    private static boolean isMeOrHuman(AgentVo a) {
        if (a == null) return false;
        if ("human".equalsIgnoreCase(a.getModel())) return true;
        return a.getTmuxSession() != null && a.getTmuxSession().startsWith("aidesk-self-");
    }

    /** 메타버스 등 외부 시각화 BE 가 소비하는 통합 realtime 응답.
     *  partners 윈도우 + offline 판정 window. */
    private static final int PARTNERS_WINDOW_SEC = 60;
    private static final int OFFLINE_THRESHOLD_SEC = 60;

    /**
     * GET /api/agents/realtime — 본인 user 의 agent 들을 state/partners/lastSeenAt 으로 합성해 반환.
     * 비인증 호출 (smoke probe 등) 은 빈 list 로 안전 fallback — /api/agents/** 가 permitAll 라
     * AuthContext.currentAccountSn() 의 throw 를 피해야 한다.
     *
     * 휴먼 entity (model='human') 는 외부 시각화 BE 에 전달하지 않는다 — 사용자(인간) 본인을
     * AI 와 같은 캐릭터로 그리지 않기 위함.
     */
    @Transactional(readOnly = true)
    public List<com.jsh.aidesk.serverapi.agents.vo.AgentRealtimeRsVo> getRealtime() {
        var user = AuthContext.currentUserOrNull();
        if (user == null) return List.of();
        List<AgentVo> rows = agentMapper.selectList(user.getAccountSn(), null);
        return rows.stream()
                .filter(v -> !"human".equalsIgnoreCase(v.getModel()))
                .map(this::toRealtime)
                .toList();
    }

    private com.jsh.aidesk.serverapi.agents.vo.AgentRealtimeRsVo toRealtime(AgentVo v) {
        List<String> partners = messageMapper.selectRecentPartners(v.getAgentId(), PARTNERS_WINDOW_SEC);
        var r = new com.jsh.aidesk.serverapi.agents.vo.AgentRealtimeRsVo();
        r.setAgentId(v.getAgentId());
        r.setName(v.getAgentName());
        r.setLastSeenAt(v.getUpdatedAt());
        r.setPartners(partners == null ? List.of() : partners);
        r.setState(resolveState(v, partners));
        return r;
    }

    private static String resolveState(AgentVo v, List<String> partners) {
        var updated = v.getUpdatedAt();
        if (updated != null
                && updated.isBefore(java.time.OffsetDateTime.now().minusSeconds(OFFLINE_THRESHOLD_SEC))) {
            return "offline";
        }
        if ("error".equalsIgnoreCase(v.getStatus())) {
            return "offline";
        }
        if (partners != null && !partners.isEmpty()) {
            return "talking";
        }
        String s = v.getStatus() == null ? "" : v.getStatus().toLowerCase();
        return switch (s) {
            case "active"  -> "working";
            case "waiting" -> "awaiting_input";
            case "idle"    -> "idle";
            default        -> "idle";
        };
    }

    @Transactional
    public AgentItemRsVo create(AgentCreateRqVo req) {
        Long me = AuthContext.currentAccountSn();
        String agentId = UUID.randomUUID().toString();
        String tmuxSession = "aidesk-" + agentId.substring(0, 8);
        String fullModel = MODEL_FULLNAMES.getOrDefault(req.getModel(), req.getModel());

        AgentVo entity = new AgentVo();
        entity.setAgentId(agentId);
        entity.setOwnerAccountSn(me);
        entity.setAgentName(req.getAgentName());
        entity.setWorkspaceDir(stripTrailingSlash(req.getWorkspaceDir()));
        entity.setTmuxSession(tmuxSession);
        entity.setStatus("active");
        entity.setModel(fullModel);
        entity.setContextPct(0);

        agentMapper.insert(entity);
        return toItem(agentMapper.selectById(agentId, me));
    }

    @Transactional
    public boolean delete(String agentId) {
        Long me = AuthContext.currentAccountSn();
        // tmux 세션 / Terminal 윈도우 정리는 프론트가 호출 직전에 헬퍼(POST /api/cleanup-agent)
        // 를 통해 본인 Mac 에서 수행. 백엔드는 DB 작업만 책임.
        // 메시지 cascade — 이 에이전트가 보내거나 받은 모든 t_ai_message row 도 함께 제거.
        // FK 제약은 없지만 orphan 메시지가 남으면 audit 시 join 결과가 깨지므로 같이 비운다.
        int msgs = messageMapper.deleteByAgent(agentId);
        int agents = agentMapper.hardDelete(agentId, me);
        if (agents > 0) {
            // 외부 AI 의 bot daemon (aidesk-bot-claude) 과 internal bot-adapter 가
            // agent.deleted event 를 받고 자가 종료하도록 ws session close.
            // ws close 자체가 봇의 reconnect-loop 도 차단 (handshake 단계 401).
            int closed = wsBroker.closeForAgent(agentId, "agent deleted");
            log.info("agent hard-deleted: agent_id={} cascaded_messages={} ws_closed={}",
                    agentId, msgs, closed);
        }
        return agents > 0;
    }

    @Transactional(readOnly = true)
    public AgentVo findById(String agentId) {
        // 비인증 (mcp) 호출은 owner 격리 없이 단건 조회. caller 가 본인 user 인지 검증 책임.
        if (AuthContext.currentUserOrNull() == null) {
            return agentMapper.selectByIdAnyOwner(agentId);
        }
        return agentMapper.selectById(agentId, AuthContext.currentAccountSn());
    }

    /**
     * Hook 또는 helper 가 본인 agent status 갱신 (예: PreCompact → 'compacting').
     * agent row 존재 + status 비어있지 않으면 update. status 값은 string free-form.
     */
    @Transactional
    public boolean updateStatus(String agentId, String status) {
        if (agentId == null || agentId.isBlank() || status == null || status.isBlank()) return false;
        AgentVo agent = agentMapper.selectByIdAnyOwner(agentId);
        if (agent == null) return false;
        int updated = agentMapper.updateStatusSystem(agentId, status);
        if (updated > 0) {
            log.info("agent status updated via hook: agent_id={} {} -> {}",
                    agentId, agent.getStatus(), status);
        }
        return updated > 0;
    }

    @Transactional(readOnly = true)
    public AgentItemRsVo detail(String agentId) {
        AgentVo v = (AuthContext.currentUserOrNull() == null)
                ? agentMapper.selectByIdAnyOwner(agentId)
                : agentMapper.selectById(agentId, AuthContext.currentAccountSn());
        return v == null ? null : toItem(v);
    }

    private AgentSummaryRsVo buildSummary(Long ownerAccountSn) {
        Map<String, Integer> counts = new HashMap<>();
        for (Map<String, Object> row : agentMapper.selectStatusCounts(ownerAccountSn)) {
            counts.put((String) row.get("status"), ((Number) row.get("cnt")).intValue());
        }
        AgentSummaryRsVo s = new AgentSummaryRsVo();
        s.setActive(counts.getOrDefault("active", 0));
        s.setWaiting(counts.getOrDefault("waiting", 0));
        // 옛 'done' row 가 DB 에 잔존하면 idle 로 합산 (마이그레이션 시점까지의 안전망)
        // 옛 'done' row 가 DB 에 잔존하면 idle 로 합산 (마이그레이션 시점까지의 안전망)
        int idle = counts.getOrDefault("idle", 0) + counts.getOrDefault("done", 0);
        s.setIdle(idle);
        s.setError(counts.getOrDefault("error", 0));
        s.setTotal(s.getActive() + s.getWaiting() + idle + s.getError());
        return s;
    }

    private AgentItemRsVo toItem(AgentVo v) {
        return toItem(v, null, null);
    }

    private AgentItemRsVo toItem(AgentVo v, AgentVo caller, Long viewerAccountSn) {
        if (v == null) return null;
        AgentItemRsVo r = new AgentItemRsVo();
        r.setAgentId(v.getAgentId());
        r.setAgentName(v.getAgentName());
        r.setWorkspaceDir(v.getWorkspaceDir());
        r.setTmuxSession(v.getTmuxSession());
        r.setStatus(v.getStatus());
        r.setTaskDesc(v.getTaskDesc());
        r.setModel(v.getModel());
        r.setContextPct(v.getContextPct());
        r.setStartedAt(v.getStartedAt());
        r.setUpdatedAt(v.getUpdatedAt());
        r.setOwnerAccountSn(v.getOwnerAccountSn());
        r.setType(resolveType(v, caller, viewerAccountSn));
        return r;
    }

    private static String stripTrailingSlash(String s) {
        if (s == null || s.length() <= 1) return s;
        return s.endsWith("/") ? s.substring(0, s.length() - 1) : s;
    }
}
