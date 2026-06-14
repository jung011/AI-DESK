package com.jsh.aidesk.serverapi.agents.watcher;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

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
 *
 * Phase 1 (Desktop Agent 도입) 이후엔 같은 일을 Helper 가 본인 Mac 에서 직접 스캔해서
 * POST /api/desktop/local-info 로 보내준다. 워처는 fallback 으로 남기되 기본 비활성.
 * 활성화하려면 application.yaml 에 `aidesk.watcher.enabled: true` 를 설정한다.
 */
@Component
@ConditionalOnProperty(name = "aidesk.watcher.enabled", havingValue = "true", matchIfMissing = false)
@RequiredArgsConstructor
@Slf4j
public class AgentStatusWatcher {

    private static final Path CLAUDE_PROJECTS_ROOT =
            Paths.get(System.getProperty("user.home"), ".claude", "projects");

    private static final long ACTIVE_WINDOW_SEC = 120;
    private static final long IDLE_WINDOW_SEC = 30 * 60;

    private final AgentMapper agentMapper;

    @Scheduled(fixedDelay = 10_000, initialDelay = 5_000)
    public void tick() {
        try {
            List<AgentVo> agents = agentMapper.selectAllForSystem();
            for (AgentVo a : agents) {
                // 옛날엔 status=done 인 에이전트를 건너뛰었지만, 사용자가 다시 작업을 시키면
                // 워처가 그대로 무시해 카드가 영원히 "완료"로 굳어졌다. 매 tick 마다 JSONL mtime
                // 으로 재평가해 active / idle / done 사이를 자유롭게 오가도록 한다.
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

        // contextPct 는 더 이상 워처가 갱신하지 않는다. 정확한 값은 statusline 이 ~/.claude/aidesk-usage/
        // 에 직접 기록하며, 카드 UI 에는 이제 표시도 안 한다. 워처가 추정값을 박아놓으면
        // context-limit-pct 정책이 잘못 작동해 메시지가 부당하게 거절된다.
        boolean statusChanged = !newStatus.equals(a.getStatus());
        if (statusChanged) {
            log.debug("watcher: agent={} status {}->{} (age={}s)",
                    a.getAgentName(), a.getStatus(), newStatus, ageSec);
            agentMapper.updateStatusFromWatcher(a.getAgentId(), newStatus, a.getContextPct());
        }
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
        // IDLE_WINDOW_SEC 초과해도 동일 idle — 'done' 상태 없음 (오래 idle 한 거지 죽은 게 아님)
        return "idle";
    }
}
