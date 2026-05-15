package com.jsh.aidesk.serverapi.agents.service;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
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
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;

import lombok.RequiredArgsConstructor;

/**
 * 에이전트 도메인의 CRUD + 요약. macOS-종속 작업(터미널/VSCode/폴더 다이얼로그) 은
 * 전부 desktop-agent (Python Helper) 로 이전되어 백엔드 컨테이너에서 실행될 수 있도록 정리됨.
 * delete() 의 tmux 정리도 향후 Helper 호출로 분리 예정.
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

    @Transactional(readOnly = true)
    public AgentListRsVo getList(String status) {
        List<AgentVo> rows = agentMapper.selectList(status);
        List<AgentItemRsVo> list = rows.stream().map(this::toItem).toList();

        AgentListRsVo rs = new AgentListRsVo();
        rs.setList(list);
        rs.setSummary(buildSummary());
        return rs;
    }

    @Transactional
    public AgentItemRsVo create(AgentCreateRqVo req) {
        String agentId = UUID.randomUUID().toString();
        String tmuxSession = "aidesk-" + agentId.substring(0, 8);
        String fullModel = MODEL_FULLNAMES.getOrDefault(req.getModel(), req.getModel());

        AgentVo entity = new AgentVo();
        entity.setAgentId(agentId);
        entity.setAgentName(req.getAgentName());
        entity.setWorkspaceDir(stripTrailingSlash(req.getWorkspaceDir()));
        entity.setTmuxSession(tmuxSession);
        entity.setStatus("active");
        entity.setModel(fullModel);
        entity.setContextPct(0);

        agentMapper.insert(entity);
        return toItem(agentMapper.selectById(agentId));
    }

    @Transactional
    public boolean delete(String agentId) {
        // 1) DB 작업 전에 tmux 세션과 그에 붙어있던 Terminal 탭을 정리한다.
        //    셸 종료만으로는 Terminal 의 "Don't close window" 프로필에서 탭이 살아남기 때문에
        //    tmux 클라이언트의 tty 를 먼저 캡처한 뒤 osascript 로 명시적으로 close.
        AgentVo v = agentMapper.selectById(agentId);
        if (v != null) {
            String tty = tmuxClientTty(v.getTmuxSession());
            killTmuxSession(v.getTmuxSession());
            if (!tty.isBlank()) closeTerminalTabByTty(tty);
        }

        // 2) 메시지 cascade — 이 에이전트가 보내거나 받은 모든 t_ai_message row 도 함께 제거.
        // FK 제약은 없지만 orphan 메시지가 남으면 audit 시 join 결과가 깨지므로 같이 비운다.
        int msgs = messageMapper.deleteByAgent(agentId);
        int agents = agentMapper.hardDelete(agentId);
        if (agents > 0) {
            log.info("agent hard-deleted: agent_id={} cascaded_messages={}", agentId, msgs);
        }
        return agents > 0;
    }

    /** tmux 세션에 attach 된 첫 번째 클라이언트의 tty 를 반환. 없으면 빈 문자열. */
    private String tmuxClientTty(String session) {
        if (session == null || session.isBlank()) return "";
        try {
            Process p = new ProcessBuilder(
                    "tmux", "list-clients", "-t", session, "-F", "#{client_tty}")
                    .redirectErrorStream(true).start();
            String out = new String(p.getInputStream().readAllBytes()).trim();
            p.waitFor();
            if (out.startsWith("can't find") || out.startsWith("no clients")) return "";
            int nl = out.indexOf('\n');
            return nl >= 0 ? out.substring(0, nl).trim() : out;
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            return "";
        }
    }

    /** tmux 세션이 살아있으면 강제 종료. 없으면 조용히 패스. */
    private void killTmuxSession(String session) {
        if (session == null || session.isBlank()) return;
        try {
            Process p = new ProcessBuilder("tmux", "kill-session", "-t", session)
                    .redirectErrorStream(true).start();
            int exit = p.waitFor();
            if (exit == 0) {
                log.info("tmux session killed: {}", session);
            }
            // exit != 0 은 세션이 이미 없을 때라 정상 — 별도 처리 없음
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("tmux kill-session failed for {}: {}", session, e.getMessage());
        }
    }

    /**
     * Terminal.app 의 모든 윈도우/탭을 훑어서 주어진 tty 에 매칭되는 탭을 닫는다.
     * 셸이 이미 깨끗하게 exit 했더라도 Terminal 프로필이 "Don't close window" 이면 탭이
     * 살아남기 때문에 이 단계가 필요하다. 매칭이 없으면 조용히 패스.
     */
    private void closeTerminalTabByTty(String tty) {
        if (tty == null || tty.isBlank()) return;
        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (!os.contains("mac")) return;
        // tmux 클라이언트 disconnect → zsh 의 `; exit 0` 후 logout 처리가 끝나기까지 약간의
        // 여유가 필요. 안 기다리면 close 가 "프로세스 종료할까요?" 다이얼로그를 띄울 수 있다.
        try { Thread.sleep(400); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        String ttyEsc = tty.replace("\\", "\\\\").replace("\"", "\\\"");
        String script = ""
                + "tell application \"Terminal\"\n"
                + "  repeat with w in windows\n"
                + "    try\n"
                + "      set matched to false\n"
                + "      repeat with t in tabs of w\n"
                + "        try\n"
                + "          if (tty of t) is \"" + ttyEsc + "\" then\n"
                + "            set matched to true\n"
                + "            exit repeat\n"
                + "          end if\n"
                + "        end try\n"
                + "      end repeat\n"
                + "      if matched then\n"
                + "        close w saving no\n"
                + "      end if\n"
                + "    end try\n"
                + "  end repeat\n"
                + "end tell\n";
        try {
            new ProcessBuilder("osascript", "-e", script).start();
            log.info("Terminal window close requested: tty={}", tty);
        } catch (IOException e) {
            log.warn("closeTerminalTabByTty failed: {}", e.getMessage());
        }
    }

    @Transactional(readOnly = true)
    public AgentVo findById(String agentId) {
        return agentMapper.selectById(agentId);
    }

    @Transactional(readOnly = true)
    public AgentItemRsVo detail(String agentId) {
        AgentVo v = agentMapper.selectById(agentId);
        return v == null ? null : toItem(v);
    }

    private AgentSummaryRsVo buildSummary() {
        Map<String, Integer> counts = new HashMap<>();
        for (Map<String, Object> row : agentMapper.selectStatusCounts()) {
            counts.put((String) row.get("status"), ((Number) row.get("cnt")).intValue());
        }
        AgentSummaryRsVo s = new AgentSummaryRsVo();
        s.setActive(counts.getOrDefault("active", 0));
        s.setIdle(counts.getOrDefault("idle", 0));
        s.setDone(counts.getOrDefault("done", 0));
        s.setTotal(s.getActive() + s.getIdle() + s.getDone());
        return s;
    }

    private AgentItemRsVo toItem(AgentVo v) {
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
        return r;
    }

    private static String stripTrailingSlash(String s) {
        if (s == null || s.length() <= 1) return s;
        return s.endsWith("/") ? s.substring(0, s.length() - 1) : s;
    }
}
