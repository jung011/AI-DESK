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

import lombok.RequiredArgsConstructor;

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
        return agentMapper.softDelete(agentId) > 0;
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

    /**
     * macOS Finder "choose folder" 다이얼로그를 띄우고 선택된 절대 경로를 반환한다.
     * 사용자가 취소하면 빈 문자열, OS 미지원이면 null.
     */
    public String browseWorkspace() {
        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (!os.contains("mac")) {
            log.warn("browseWorkspace: unsupported OS '{}'", os);
            return null;
        }
        try {
            Process p = new ProcessBuilder(
                    "osascript", "-e",
                    "POSIX path of (choose folder with prompt \"워크스페이스 폴더를 선택하세요\")"
            ).redirectErrorStream(true).start();
            String out = new String(p.getInputStream().readAllBytes()).trim();
            int exit = p.waitFor();
            if (exit != 0) {
                // 사용자가 취소하면 osascript 가 비-0 + "User canceled" 출력. 정상 흐름.
                log.debug("browseWorkspace: osascript exit={} out={}", exit, out);
                return "";
            }
            // 트레일링 슬래시 제거 (insert 시 stripTrailingSlash 와 동일 규칙)
            return stripTrailingSlash(out);
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("browseWorkspace failed: {}", e.getMessage());
            return null;
        }
    }

    /**
     * 에이전트의 워크스페이스 디렉토리를 macOS Terminal 로 연다.
     * 백엔드와 사용자가 같은 머신을 쓰는 PoC 환경 한정으로 동작.
     *
     * @return 0 = 성공, 1 = agent 없음, 2 = workspace 비어있음, 3 = OS 미지원, 4 = 실행 실패
     */
    public int openTerminal(String agentId) {
        AgentVo v = agentMapper.selectById(agentId);
        if (v == null) return 1;
        String dir = v.getWorkspaceDir();
        if (dir == null || dir.isBlank()) return 2;

        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (!os.contains("mac")) {
            log.warn("openTerminal: unsupported OS '{}'", os);
            return 3;
        }

        try {
            new ProcessBuilder("open", "-a", "Terminal", dir).start();
            log.info("openTerminal: agent={} dir={}", v.getAgentName(), dir);
            return 0;
        } catch (IOException e) {
            log.warn("openTerminal failed: {}", e.getMessage());
            return 4;
        }
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
