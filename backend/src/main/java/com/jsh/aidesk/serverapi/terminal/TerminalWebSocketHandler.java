package com.jsh.aidesk.serverapi.terminal;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;
import org.springframework.web.util.UriComponentsBuilder;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.pty4j.PtyProcess;
import com.pty4j.PtyProcessBuilder;
import com.pty4j.WinSize;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * xterm.js ↔ tmux PTY 양방향 펌프.
 *
 * 프로토콜:
 *   - 클라이언트 → 서버: 일반 텍스트 = stdin 입력. JSON `{"type":"resize","cols":N,"rows":N}` = PTY 리사이즈.
 *   - 서버 → 클라이언트: PTY stdout 의 raw 바이트를 UTF-8 텍스트로 전달.
 *
 * 세션 수명:
 *   - WS 연결 시 `tmux new-session -A -s {sessionName}` PTY 생성 (이미 있으면 attach, 없으면 신규).
 *   - WS 종료 시 PTY destroy (tmux 세션 자체는 detach 만 됨 — 세션은 서버에서 계속 유지).
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class TerminalWebSocketHandler extends AbstractWebSocketHandler {

    /** tmux 세션명 안전 문자 (xterm 임의 입력으로부터 쉘 인젝션 방지). */
    private static final Pattern SESSION_NAME = Pattern.compile("^[A-Za-z0-9_-]{1,64}$");
    /** PTY → WS 펌프 버퍼 크기. */
    private static final int READ_BUFFER = 4096;
    /** xterm.js 초기 그리드 크기 — 클라이언트가 첫 resize 보낼 때까지의 fallback. */
    private static final int DEFAULT_COLS = 120;
    private static final int DEFAULT_ROWS = 30;

    private final AgentMapper agentMapper;

    private final ObjectMapper mapper = new ObjectMapper();
    private final Map<String, PtyProcess> processes = new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession ws) throws Exception {
        String session = queryParam(ws.getUri(), "session");
        if (session == null || !SESSION_NAME.matcher(session).matches()) {
            log.warn("terminal WS rejected: invalid session name '{}'", session);
            ws.close(new CloseStatus(4400, "invalid session name"));
            return;
        }

        // 신규 tmux 세션이면 에이전트의 workspaceDir 로 cd + 모델에 맞는 CLI(claude/codex/hermes)
        // 를 자동 기동한다. 기존 세션 attach 시엔 둘 다 tmux 가 무시하므로 안전.
        AgentVo agent = lookupAgent(session);
        String workspaceDir = agent != null && agent.getWorkspaceDir() != null
                && !agent.getWorkspaceDir().isBlank() ? agent.getWorkspaceDir() : null;
        String cliCommand = resolveCliCommand(agent, workspaceDir);

        String[] command = cliCommand == null
                ? new String[]{"tmux", "new-session", "-A", "-s", session}
                : new String[]{"tmux", "new-session", "-A", "-s", session, cliCommand};

        PtyProcessBuilder builder = new PtyProcessBuilder()
                .setCommand(command)
                .setEnvironment(System.getenv())
                .setConsole(false)
                .setInitialColumns(DEFAULT_COLS)
                .setInitialRows(DEFAULT_ROWS);
        if (workspaceDir != null) builder.setDirectory(workspaceDir);

        PtyProcess pty;
        try {
            pty = builder.start();
        } catch (IOException e) {
            log.warn("terminal WS PTY spawn failed: session={} err={}", session, e.getMessage());
            ws.close(new CloseStatus(4500, "pty spawn failed"));
            return;
        }
        processes.put(ws.getId(), pty);
        log.info("terminal WS open: wsId={} tmux={} pid={}", ws.getId(), session, pty.pid());

        // PTY stdout → WS 펌프 (가상 스레드 — 다수 동시 터미널에도 가볍게 대응)
        final PtyProcess captured = pty;
        Thread.startVirtualThread(() -> pumpOutput(ws, captured));
    }

    @Override
    protected void handleTextMessage(WebSocketSession ws, TextMessage msg) throws Exception {
        PtyProcess pty = processes.get(ws.getId());
        if (pty == null) return;
        String payload = msg.getPayload();

        // 제어 메시지 (JSON) 와 일반 입력 (그 외 모든 텍스트) 구분.
        // JSON 모양이 아닌 페이로드는 그대로 stdin 으로 — 일반 키 입력의 핫패스는 파싱 비용 회피.
        if (!payload.isEmpty() && payload.charAt(0) == '{') {
            try {
                JsonNode root = mapper.readTree(payload);
                String type = root.path("type").asText("");
                if ("resize".equals(type)) {
                    int cols = root.path("cols").asInt(DEFAULT_COLS);
                    int rows = root.path("rows").asInt(DEFAULT_ROWS);
                    pty.setWinSize(new WinSize(cols, rows));
                    return;
                }
                if ("input".equals(type)) {
                    writeStdin(pty, root.path("data").asText(""));
                    return;
                }
                // 알 수 없는 control type — 안전하게 무시
                log.debug("terminal WS unknown control: {}", type);
                return;
            } catch (Exception ignore) {
                // JSON 파싱 실패면 일반 입력으로 폴백 (사용자가 `{` 를 친 케이스)
            }
        }
        writeStdin(pty, payload);
    }

    @Override
    public void afterConnectionClosed(WebSocketSession ws, CloseStatus status) {
        PtyProcess pty = processes.remove(ws.getId());
        if (pty != null) {
            log.info("terminal WS close: wsId={} status={}", ws.getId(), status);
            pty.destroy();
        }
    }

    @Override
    public void handleTransportError(WebSocketSession ws, Throwable ex) {
        log.warn("terminal WS transport error: wsId={} err={}", ws.getId(), ex.getMessage());
    }

    private void pumpOutput(WebSocketSession ws, PtyProcess pty) {
        byte[] buf = new byte[READ_BUFFER];
        try (InputStream in = pty.getInputStream()) {
            int n;
            while ((n = in.read(buf)) >= 0) {
                if (!ws.isOpen()) break;
                String chunk = new String(buf, 0, n, StandardCharsets.UTF_8);
                synchronized (ws) {
                    ws.sendMessage(new TextMessage(chunk));
                }
            }
        } catch (IOException e) {
            log.debug("terminal WS pty stdout closed: wsId={} err={}", ws.getId(), e.getMessage());
        } finally {
            try {
                if (ws.isOpen()) ws.close();
            } catch (IOException ignored) { /* 이미 닫힌 채널 */ }
        }
    }

    private void writeStdin(PtyProcess pty, String s) throws IOException {
        OutputStream out = pty.getOutputStream();
        out.write(s.getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    /** tmux_session 컬럼으로 에이전트를 찾는다. 미등록 세션(PoC 등) 이면 null. */
    private AgentVo lookupAgent(String session) {
        try {
            return agentMapper.selectByTmuxSession(session);
        } catch (Exception e) {
            log.debug("lookupAgent failed: session={} err={}", session, e.getMessage());
            return null;
        }
    }

    /**
     * 신규 tmux 세션에서 자동 기동할 CLI 명령 한 줄을 반환. 등록된 에이전트가 없으면 null
     * 을 돌려 셸만 띄운다. 모델 매핑은 AgentService.resolveCliCommand 와 동일하지만 의존
     * 사이클 회피를 위해 핸들러에 작게 복제. (M7 이후 별도 컴포넌트로 추출 후보)
     */
    private String resolveCliCommand(AgentVo agent, String workspaceDir) {
        if (agent == null) return null;
        String model = agent.getModel();
        if (model == null || model.isBlank()) return claudeCmdWithResume(workspaceDir);
        if (model.startsWith("claude")) return claudeCmdWithResume(workspaceDir);
        if ("codex".equals(model)) return "codex";
        if ("hermes".equals(model)) return "hermes";
        log.warn("unknown model '{}' — falling back to claude", model);
        return claudeCmdWithResume(workspaceDir);
    }

    /** 워크스페이스에 옛 Claude Code JSONL 이 남아있으면 자동 `claude -c` 로 resume. */
    private String claudeCmdWithResume(String workspaceDir) {
        if (workspaceDir == null || workspaceDir.isBlank()) return "claude";
        String escaped = workspaceDir.replaceAll("[^A-Za-z0-9_]", "-");
        Path projDir = Paths.get(System.getProperty("user.home"), ".claude", "projects", escaped);
        if (!Files.isDirectory(projDir)) return "claude";
        try (Stream<Path> stream = Files.walk(projDir, 5)) {
            boolean hasJsonl = stream.anyMatch(p -> p.toString().endsWith(".jsonl") && Files.isRegularFile(p));
            return hasJsonl ? "claude -c" : "claude";
        } catch (IOException e) {
            return "claude";
        }
    }

    private static String queryParam(URI uri, String key) {
        if (uri == null) return null;
        return UriComponentsBuilder.fromUri(uri).build()
                .getQueryParams().getFirst(key);
    }
}
