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
import java.util.stream.Stream;

import org.springframework.beans.factory.annotation.Value;
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

    /**
     * 새 tmux 세션이 처음 만들어진 직후 claude 에 자동 주입할 첫 프롬프트.
     * 비어있으면 주입을 건너뛴다.
     */
    @Value("${agents.bootstrap-prompt:}")
    private String bootstrapPrompt;
    /** claude 부팅 후 첫 프롬프트가 그려질 때까지 대기 (ms). */
    private static final long BOOTSTRAP_DELAY_MS = 4_000;

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
        // 탭 단위 close 는 1탭 윈도우에서 동작하지 않는 경우가 있어 윈도우 단위로 close 한다.
        // (do script 는 매 호출마다 새 윈도우를 만들므로 보통 1탭/윈도우 — 안전하다)
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
        String titleEsc = (v.getAgentName() == null ? session : v.getAgentName())
                .replace("\\", "\\\\").replace("\"", "\\\"");
        // 에이전트의 model 필드에 맞춰 실제 CLI 를 선택. claude 만 -c resume 을 지원하고,
        // codex / hermes 는 자체 resume 메커니즘 정해지면 별도로 다시 손본다.
        String claudeCmd = resolveCliCommand(v.getModel(), dir);
        String script = ""
                + "set sessionName to \"" + session + "\"\n"
                + "set wsQuoted to quoted form of \"" + dirEsc + "\"\n"
                + "set tabTitle to \"" + titleEsc + "\"\n"
                // 끝에 `; exit 0` — tmux 가 (사용자 종료/kill-session 등 어떤 경로로든) 끝나면
                // 부모 zsh 도 exit 0 으로 같이 종료되도록 한다. Terminal 기본 프로필 "shell exited
                // cleanly → close window" 가 동작해서 [에이전트 삭제] 후 빈 윈도우가 남지 않는다.
                // (tmux 클라이언트가 kill-session 으로 강제 종료될 때 비-0 을 반환해도 우리는 0 으로 회수)
                + "set shellCmd to \"cd \" & wsQuoted & \" && tmux new-session -A -s \" & sessionName & \" '" + claudeCmd + "'; exit 0\"\n"
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
                + "    set newTab to do script shellCmd\n"
                + "    try\n"
                + "      set font size of newTab to 14\n"
                + "    end try\n"
                + "    try\n"
                + "      set custom title of newTab to tabTitle\n"
                + "    end try\n"
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
                + "      set newTab to do script shellCmd in selected tab of front window\n"
                + "    else\n"
                + "      set newTab to do script shellCmd\n"
                + "    end if\n"
                + "    try\n"
                + "      set font size of newTab to 14\n"
                + "    end try\n"
                + "    try\n"
                + "      set custom title of newTab to tabTitle\n"
                + "    end try\n"
                + "  end tell\n"
                + "end if\n";

        // 신규 tmux 세션을 만들 케이스인지 미리 판단. 부트스트랩은 다음 두 조건이 모두 참일 때만:
        //   1) tmux 세션이 살아있지 않다 — 살아있으면 그냥 attach 라 작업 중인 세션을 침범하면 안 됨
        //   2) 이 에이전트(t_ai_agent.agent_id) 가 아직 부트스트랩을 받아본 적이 없다
        //
        // (참고) 워크스페이스에 옛 jsonl 이 있어도 그건 다른 에이전트의 흔적일 수 있으므로
        // jsonl 존재 여부로 판단하지 않는다 — 사용자가 [AI 생성] 으로 만든 에이전트는 한 번은
        // workrole 을 학습하도록 보장.
        boolean freshSession = !tmuxHasSession(session);
        boolean injectBootstrap =
                freshSession
                        && !v.isBootstrapApplied()
                        && bootstrapPrompt != null
                        && !bootstrapPrompt.isBlank();

        try {
            new ProcessBuilder("osascript", "-e", script).start();
            log.info("openTerminal: agent={} dir={} session={} fresh={} cli={} alreadyBootstrapped={} willInject={}",
                    v.getAgentName(), dir, session, freshSession, claudeCmd,
                    v.isBootstrapApplied(), injectBootstrap);
            if (injectBootstrap) {
                final String tgt = session;
                final String agentId2 = agentId;
                final String model = v.getModel();
                Thread.startVirtualThread(() -> {
                    sendBootstrapPrompt(tgt, model);
                    agentMapper.markBootstrapApplied(agentId2);
                });
            }
            return 0;
        } catch (IOException e) {
            log.warn("openTerminal failed: {}", e.getMessage());
            return 4;
        }
    }

    /**
     * 에이전트가 생성될 때 저장된 풀모델(claude-opus-4-7 / codex / hermes 등) 을
     * 실제로 tmux 안에서 실행할 CLI 한 줄로 변환한다.
     *
     *   - claude  계열  → `claude` (또는 워크스페이스에 옛 jsonl 있으면 `claude -c`)
     *   - codex          → `codex`
     *   - hermes         → `hermes`
     *
     * 빈 값이나 미지의 모델은 claude 로 폴백 + 경고 로그.
     */
    private String resolveCliCommand(String fullModel, String workspaceDir) {
        if (fullModel == null || fullModel.isBlank()) {
            log.warn("resolveCliCommand: model empty — falling back to claude");
            return claudeCmdWithResume(workspaceDir);
        }
        if (fullModel.startsWith("claude")) return claudeCmdWithResume(workspaceDir);
        if ("codex".equals(fullModel))  return "codex";
        if ("hermes".equals(fullModel)) return "hermes";
        log.warn("resolveCliCommand: unknown model '{}' — falling back to claude", fullModel);
        return claudeCmdWithResume(workspaceDir);
    }

    /** claude 만 워크스페이스에 옛 JSONL 이 남아있으면 자동으로 -c resume 한다. */
    private String claudeCmdWithResume(String workspaceDir) {
        return workspaceHasPastSession(workspaceDir) ? "claude -c" : "claude";
    }

    /**
     * 워크스페이스 dir 에 매칭되는 ~/.claude/projects/{escaped}/ 안에 .jsonl 이 하나라도
     * 있으면 옛 Claude Code 대화가 존재한다고 본다. AgentStatusWatcher 와 같은 escape 규칙
     * (영숫자/언더스코어 외 모두 '-') 을 사용한다.
     */
    private boolean workspaceHasPastSession(String workspaceDir) {
        if (workspaceDir == null || workspaceDir.isBlank()) return false;
        String escaped = workspaceDir.replaceAll("[^A-Za-z0-9_]", "-");
        Path projDir = Paths.get(System.getProperty("user.home"), ".claude", "projects", escaped);
        if (!Files.isDirectory(projDir)) return false;
        try (Stream<Path> stream = Files.walk(projDir, 5)) {
            return stream
                    .filter(Files::isRegularFile)
                    .anyMatch(p -> p.getFileName().toString().endsWith(".jsonl"));
        } catch (IOException e) {
            log.warn("workspaceHasPastSession walk {} failed: {}", projDir, e.getMessage());
            return false;
        }
    }

    private boolean tmuxHasSession(String session) {
        try {
            Process p = new ProcessBuilder("tmux", "has-session", "-t", session)
                    .redirectErrorStream(true).start();
            return p.waitFor() == 0;
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            return false;
        }
    }

    /**
     * 새로 띄운 LLM CLI 가 첫 프롬프트를 그릴 때까지 잠시 대기한 뒤 부트스트랩 프롬프트를
     * tmux send-keys 로 주입한다. literal 모드 + 별도 Enter 로 분리해 paste-detect 가
     * Enter 를 흡수하지 않게 한다 (TmuxLastMileAdapter 와 같은 패턴).
     *
     * 모델별 차이:
     *   - claude   — paste-detect 가 200ms 안에 끝남. 부팅 4s 면 충분.
     *   - hermes/codex — REPL/입력 처리 속도가 더 느릴 수 있어 부팅 대기 +2s, Enter 직전
     *                    공백 800ms 로 늘려 입력 누락을 막는다.
     */
    private void sendBootstrapPrompt(String session, String model) {
        boolean isClaude = model != null && model.startsWith("claude");
        long bootDelay = isClaude ? BOOTSTRAP_DELAY_MS : BOOTSTRAP_DELAY_MS + 2_000L;
        long enterGap  = isClaude ? 200L : 800L;
        try {
            Thread.sleep(bootDelay);
            new ProcessBuilder("tmux", "send-keys", "-l", "-t", session, bootstrapPrompt)
                    .redirectErrorStream(true).start().waitFor();
            Thread.sleep(enterGap);
            new ProcessBuilder("tmux", "send-keys", "-t", session, "Enter")
                    .redirectErrorStream(true).start().waitFor();
            log.info("bootstrap prompt injected into tmux session {} (model={}, bootDelay={}ms, enterGap={}ms)",
                    session, model, bootDelay, enterGap);
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("bootstrap prompt failed: {}", e.getMessage());
        }
    }

    /**
     * 에이전트의 워크스페이스를 VSCode 에 띄운다.
     *
     * 동작:
     *   - 같은 폴더가 이미 열려있으면 → VSCode 가 그 윈도우를 활성화 (기본 동작)
     *   - 다른 폴더면 → 새 윈도우 (기존 작업 윈도우는 그대로 유지)
     *
     * `-r` 플래그는 사용하지 않는다 — 그건 "현재 윈도우를 이 폴더로 교체" 라
     * 다른 프로젝트 작업 중이던 윈도우를 덮어버린다.
     *
     * code 바이너리 후보 순서:
     *   1) 로그인 셸 PATH 의 `code` (사용자가 "Install code in PATH" 한 경우)
     *   2) macOS Spotlight (`mdfind`) 로 찾은 VSCode.app 번들 안의 code 바이너리
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
        if (runOk(new ProcessBuilder("/bin/zsh", "-l", "-c", "code " + quoted))) {
            log.info("openVscode (PATH): agent={} dir={}", v.getAgentName(), dir);
            return 0;
        }

        // 2) VSCode.app 번들 안의 code 바이너리
        String bundled = locateVscodeBundled();
        if (bundled != null && runOk(new ProcessBuilder(bundled, dir))) {
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
