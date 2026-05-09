package com.jsh.aidesk.serverapi.agents.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
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
     * 에이전트의 워크스페이스에서 Terminal 을 열고 tmux 세션에서 claude 를 실행한다.
     *
     * 동작 우선순위:
     *   1) 같은 tmux 세션에 이미 attach 된 Terminal tab 이 있으면 → 그 윈도우/탭 활성화 (새 윈도우 생성 X)
     *   2) 없으면 → 새 윈도우에서 cd + tmux new-session -A -s {session} 'claude'
     *
     * @return 0 = 성공, 1 = agent 없음, 2 = workspace 비어있음, 3 = OS 미지원, 4 = 실행 실패
     */
    public int openTerminal(String agentId) {
        AgentVo v = agentMapper.selectById(agentId);
        if (v == null) return 1;
        String dir = v.getWorkspaceDir();
        if (dir == null || dir.isBlank()) return 2;
        String session = v.getTmuxSession();
        if (session == null || session.isBlank()) {
            session = "aidesk-" + agentId.substring(0, Math.min(8, agentId.length()));
        }

        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (!os.contains("mac")) {
            log.warn("openTerminal: unsupported OS '{}'", os);
            return 3;
        }

        String dirEsc = dir.replace("\\", "\\\\").replace("\"", "\\\"");
        String script = ""
                + "set sessionName to \"" + session + "\"\n"
                + "set wsQuoted to quoted form of \"" + dirEsc + "\"\n"
                + "set shellCmd to \"cd \" & wsQuoted & \" && tmux new-session -A -s \" & sessionName & \" 'claude'\"\n"
                // Terminal.app 이 이미 떠있는지 셸로 먼저 확인. tell application "Terminal" 안에서 count windows
                // 류를 호출하면 그 자체로 Terminal 이 launch 되며 기본 윈도우 1개가 생기기 때문.
                + "set termRunning to false\n"
                + "try\n"
                + "  do shell script \"pgrep -x Terminal > /dev/null\"\n"
                + "  set termRunning to true\n"
                + "end try\n"
                + "set clientTty to \"\"\n"
                + "try\n"
                + "  set clientTty to do shell script \"tmux list-clients -t \" & sessionName & \" -F '#{client_tty}' 2>/dev/null | head -n 1\"\n"
                + "end try\n"
                + "if clientTty is not \"\" then\n"
                + "  tell application \"Terminal\"\n"
                + "    activate\n"
                + "    repeat with w in windows\n"
                + "      repeat with t in tabs of w\n"
                + "        try\n"
                + "          if (tty of t) is clientTty then\n"
                + "            set frontmost of w to true\n"
                + "            set selected of t to true\n"
                + "            return\n"
                + "          end if\n"
                + "        end try\n"
                + "      end repeat\n"
                + "    end repeat\n"
                + "  end tell\n"
                + "end if\n"
                + "if termRunning then\n"
                // Terminal 이미 가동 중 — 새 윈도우를 만들어 사용자의 다른 작업 윈도우를 침범하지 않음.
                + "  tell application \"Terminal\"\n"
                + "    activate\n"
                + "    do script shellCmd\n"
                + "  end tell\n"
                + "else\n"
                // Terminal 꺼져 있음 — launch 가 자동 생성하는 기본 윈도우를 재사용.
                + "  tell application \"Terminal\"\n"
                + "    launch\n"
                + "    repeat 30 times\n"
                + "      if (count windows) > 0 then exit repeat\n"
                + "      delay 0.1\n"
                + "    end repeat\n"
                + "    activate\n"
                + "    if (count windows) > 0 then\n"
                + "      do script shellCmd in selected tab of front window\n"
                + "    else\n"
                + "      do script shellCmd\n"
                + "    end if\n"
                + "  end tell\n"
                + "end if\n";

        try {
            new ProcessBuilder("osascript", "-e", script).start();
            log.info("openTerminal: agent={} dir={} session={}", v.getAgentName(), dir, session);
            return 0;
        } catch (IOException e) {
            log.warn("openTerminal failed: {}", e.getMessage());
            return 4;
        }
    }

    /**
     * 에이전트의 워크스페이스를 VSCode 의 기존 윈도우에 띄운다 (`code -r`).
     *
     * code 바이너리 후보 순서:
     *   1) 로그인 셸 PATH 의 `code` (사용자가 "Install code in PATH" 한 경우)
     *   2) macOS Spotlight (`mdfind`) 로 찾은 VSCode.app 번들 안의 code 바이너리
     *
     * 둘 다 실패하면 4 반환 — 사용자에게 설치 안내.
     *
     * @return 0 = 성공, 1 = agent 없음, 2 = workspace 비어있음, 3 = OS 미지원, 4 = code 미발견/실행 실패
     */
    public int openVscode(String agentId) {
        AgentVo v = agentMapper.selectById(agentId);
        if (v == null) return 1;
        String dir = v.getWorkspaceDir();
        if (dir == null || dir.isBlank()) return 2;

        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (!os.contains("mac")) {
            log.warn("openVscode: unsupported OS '{}'", os);
            return 3;
        }

        // 1) PATH 의 code
        String quoted = "'" + dir.replace("'", "'\\''") + "'";
        if (runOk(new ProcessBuilder("/bin/zsh", "-l", "-c", "code -r " + quoted))) {
            log.info("openVscode (PATH): agent={} dir={}", v.getAgentName(), dir);
            return 0;
        }

        // 2) VSCode.app 번들 안의 code 바이너리
        String bundled = locateVscodeBundled();
        if (bundled != null && runOk(new ProcessBuilder(bundled, "-r", dir))) {
            log.info("openVscode (bundled): agent={} via {}", v.getAgentName(), bundled);
            return 0;
        }

        log.warn("openVscode: failed (no code in PATH and bundled lookup={})", bundled);
        return 4;
    }

    private static boolean runOk(ProcessBuilder pb) {
        try {
            Process p = pb.redirectErrorStream(true).start();
            int exit = p.waitFor();
            return exit == 0;
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            return false;
        }
    }

    private static String locateVscodeBundled() {
        try {
            Process p = new ProcessBuilder(
                    "mdfind", "kMDItemCFBundleIdentifier == 'com.microsoft.VSCode'"
            ).redirectErrorStream(true).start();
            String out = new String(p.getInputStream().readAllBytes()).trim();
            p.waitFor();
            if (out.isEmpty()) return null;
            for (String hit : out.split("\\R")) {
                Path bin = Paths.get(hit, "Contents/Resources/app/bin/code");
                if (Files.isExecutable(bin)) return bin.toString();
            }
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
        }
        return null;
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
