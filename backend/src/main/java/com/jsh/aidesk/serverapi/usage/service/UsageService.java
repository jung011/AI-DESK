package com.jsh.aidesk.serverapi.usage.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jsh.aidesk.serverapi.usage.vo.LocalUsageRsVo;

import lombok.extern.slf4j.Slf4j;

/**
 * 로컬 머신의 Claude Code 통합 사용량.
 *
 * 정의: ~/.claude/projects 아래 모든 JSONL 중 mtime 이 가장 최근인 파일 → 그 파일의
 * 가장 최근 message.usage → (input + cache_read + cache_creation) 토큰 수.
 * 분모는 현재 1,000,000 고정 (1M 컨텍스트 모델 기준).
 *
 * 한 머신에 여러 Claude Code 세션이 떠 있으면 가장 최근 활동 세션을 보여준다.
 */
@Service
@Slf4j
public class UsageService {

    private static final Path CLAUDE_PROJECTS_ROOT =
            Paths.get(System.getProperty("user.home"), ".claude", "projects");

    private static final long CONTEXT_WINDOW_TOKENS = 1_000_000L;

    private final ObjectMapper objectMapper = new ObjectMapper();

    public LocalUsageRsVo getLocalUsage() {
        LocalUsageRsVo rs = new LocalUsageRsVo();
        rs.setWindow(CONTEXT_WINDOW_TOKENS);
        rs.setSource("");
        rs.setTokens(0);
        rs.setPct(0);

        if (!Files.isDirectory(CLAUDE_PROJECTS_ROOT)) return rs;

        Path latest = findLatestJsonl(CLAUDE_PROJECTS_ROOT);
        if (latest == null) return rs;

        long tokens = readLatestUsageTokens(latest);
        if (tokens <= 0) {
            rs.setSource(latest.toString());
            return rs;
        }

        long pct = tokens * 100 / CONTEXT_WINDOW_TOKENS;
        rs.setTokens(tokens);
        rs.setPct((int) Math.min(100, Math.max(0, pct)));
        rs.setSource(latest.toString());
        return rs;
    }

    private Path findLatestJsonl(Path root) {
        try (Stream<Path> stream = Files.walk(root, 6)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".jsonl"))
                    .max(Comparator.comparingLong(p -> p.toFile().lastModified()))
                    .orElse(null);
        } catch (IOException e) {
            log.warn("usage: walk {} failed: {}", root, e.getMessage());
            return null;
        }
    }

    private long readLatestUsageTokens(Path jsonl) {
        try {
            List<String> lines = Files.readAllLines(jsonl);
            for (int i = lines.size() - 1; i >= 0; i--) {
                String line = lines.get(i).trim();
                if (line.isEmpty() || !line.startsWith("{")) continue;
                try {
                    JsonNode root = objectMapper.readTree(line);
                    JsonNode usage = root.path("message").path("usage");
                    if (usage.isMissingNode() || usage.isEmpty()) continue;
                    long tokens = usage.path("input_tokens").asLong(0)
                            + usage.path("cache_read_input_tokens").asLong(0)
                            + usage.path("cache_creation_input_tokens").asLong(0);
                    if (tokens > 0) return tokens;
                } catch (Exception ignore) {
                    // 깨진 라인은 위로 계속 탐색
                }
            }
        } catch (IOException e) {
            log.warn("usage: read jsonl {} failed: {}", jsonl, e.getMessage());
        }
        return 0;
    }
}
