package com.jsh.aidesk.serverapi.agents.watcher;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * AI 세션 파일 (Claude Code JSONL 등) 의 최신 수정 시각으로 status 를 자동 갱신한다.
 *
 * 추정 규칙:
 *   2분 이내 → active, 2분~30분 → idle, 30분 초과 또는 파일 없음 → done
 *
 * 1단계 PoC 범위:
 *   - claude 모델만 처리. codex / hermes 는 spec TBD 라 건너뜀.
 *   - workspace_dir 을 escape 하여 ~/.claude/projects/{escaped}/ 디렉토리 매칭.
 *   - 디렉토리 부재 / .jsonl 부재 시 갱신 스킵 (시드 데이터 보호).
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class AgentStatusWatcher {

    private static final Path CLAUDE_PROJECTS_ROOT =
            Paths.get(System.getProperty("user.home"), ".claude", "projects");

    private static final long ACTIVE_WINDOW_SEC = 120;
    private static final long IDLE_WINDOW_SEC = 30 * 60;

    // 모델별 컨텍스트 윈도우. 1M 변형은 모델 ID 가 `[1m]` 으로 끝남.
    private static final long CTX_DEFAULT_TOKENS = 200_000L;
    private static final long CTX_1M_TOKENS = 1_000_000L;

    private final AgentMapper agentMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Scheduled(fixedDelay = 10_000, initialDelay = 5_000)
    public void tick() {
        try {
            List<AgentVo> agents = agentMapper.selectList(null);
            for (AgentVo a : agents) {
                if ("done".equals(a.getStatus())) continue;
                if (!isClaudeModel(a.getModel())) continue;
                checkAndUpdate(a);
            }
        } catch (Exception e) {
            log.warn("AgentStatusWatcher tick failed: {}", e.getMessage());
        }
    }

    private void checkAndUpdate(AgentVo a) {
        Path projectDir = projectDirOf(a.getWorkspaceDir());
        if (projectDir == null || !Files.isDirectory(projectDir)) {
            return; // 매칭되는 jsonl 디렉토리 없음 — 1단계 스킵
        }
        Path latest = findLatestJsonl(projectDir);
        if (latest == null) return;

        long ageSec = (System.currentTimeMillis() - latest.toFile().lastModified()) / 1000;
        String newStatus = estimateStatus(ageSec);
        Integer newCtx = computeContextPct(latest);

        boolean statusChanged = !newStatus.equals(a.getStatus());
        boolean ctxChanged = newCtx != null && !newCtx.equals(a.getContextPct());

        if (statusChanged || ctxChanged) {
            log.debug("watcher: agent={} status {}->{} ctx {}->{} (age={}s)",
                    a.getAgentName(), a.getStatus(), newStatus,
                    a.getContextPct(), newCtx, ageSec);
            agentMapper.updateStatusFromWatcher(a.getAgentId(), newStatus, newCtx);
        }
    }

    /**
     * JSONL 의 마지막 message.usage 를 추출해 Claude Code `/usage` 와 같은 형태로 컨텍스트 % 환산.
     *
     * 분자: input + cache_read + cache_creation (= 그 턴의 prompt 크기). output 은 컨텍스트 입력이 아니므로 제외.
     * 분모: 모델 ID 의 `[1m]` 접미사 유무에 따라 1,000,000 또는 200,000.
     *
     * Claude Code `/usage` 와 미세하게(±몇 %) 다를 수 있다 — 내부 시스템 프롬프트/예약 마진을 알 수 없기 때문.
     */
    private Integer computeContextPct(Path jsonl) {
        try {
            List<String> lines = Files.readAllLines(jsonl);
            for (int i = lines.size() - 1; i >= 0; i--) {
                String line = lines.get(i).trim();
                if (line.isEmpty() || !line.startsWith("{")) continue;
                try {
                    JsonNode root = objectMapper.readTree(line);
                    JsonNode message = root.path("message");
                    JsonNode usage = message.path("usage");
                    if (usage.isMissingNode() || usage.isEmpty()) continue;
                    long tokens = 0;
                    tokens += usage.path("input_tokens").asLong(0);
                    tokens += usage.path("cache_read_input_tokens").asLong(0);
                    tokens += usage.path("cache_creation_input_tokens").asLong(0);
                    if (tokens == 0) continue;

                    String model = message.path("model").asText("");
                    long window = contextWindowOf(model);
                    long pct = tokens * 100 / window;
                    return (int) Math.min(100, Math.max(0, pct));
                } catch (Exception ignore) {
                    // 깨진 라인은 건너뛰고 계속 위로 탐색
                }
            }
        } catch (IOException e) {
            log.warn("watcher: read jsonl {} failed: {}", jsonl, e.getMessage());
        }
        return null;
    }

    private static long contextWindowOf(String model) {
        // 1M 변형 모델 ID 는 `[1m]` 으로 끝난다. 그 외는 200k 가정.
        if (model != null && model.endsWith("[1m]")) return CTX_1M_TOKENS;
        return CTX_DEFAULT_TOKENS;
    }

    private static boolean isClaudeModel(String model) {
        return model != null && model.startsWith("claude");
    }

    /**
     * workspace_dir 을 ~/.claude/projects 의 디렉토리명으로 escape.
     * Claude Code 가 cwd 를 폴더명으로 변환할 때 영숫자/언더스코어 외 문자를 '-' 로 치환하므로
     * 동일 규칙을 적용 (슬래시·공백·점 등 모두 '-').
     */
    private static Path projectDirOf(String workspaceDir) {
        if (workspaceDir == null || workspaceDir.isBlank()) return null;
        String escaped = workspaceDir.replaceAll("[^A-Za-z0-9_]", "-");
        return CLAUDE_PROJECTS_ROOT.resolve(escaped);
    }

    private static Path findLatestJsonl(Path dir) {
        // Claude Code 는 ~/.claude/projects/{escaped}/{session-id}/.../*.jsonl 형태로
        // subagent 단위 폴더에 jsonl 을 둔다. 깊이 5 까지 recursively 검색.
        try (Stream<Path> stream = Files.walk(dir, 5)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".jsonl"))
                    .max(Comparator.comparingLong(p -> p.toFile().lastModified()))
                    .orElse(null);
        } catch (IOException e) {
            log.warn("watcher: walk {} failed: {}", dir, e.getMessage());
            return null;
        }
    }

    private static String estimateStatus(long ageSec) {
        if (ageSec <= ACTIVE_WINDOW_SEC) return "active";
        if (ageSec <= IDLE_WINDOW_SEC) return "idle";
        return "done";
    }
}
