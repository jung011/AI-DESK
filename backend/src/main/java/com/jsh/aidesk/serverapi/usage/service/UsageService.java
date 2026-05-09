package com.jsh.aidesk.serverapi.usage.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jsh.aidesk.serverapi.usage.vo.LocalUsageRsVo;

import lombok.extern.slf4j.Slf4j;

/**
 * 로컬 Claude Code 사용량.
 *
 * 데이터 소스: ~/.claude/aidesk-usage/{sessionId}.json — adesk-cli 의 statusline 스크립트가
 * Claude Code 의 statusLine 콜백에서 받은 JSON (rate_limits, context_window) 을 기록한 파일.
 * 가장 최근 mtime 의 세션 파일을 읽어 그 값을 그대로 노출 → /usage 와 동일 값.
 *
 * 스크립트 미설치 시 디렉토리/파일 자체가 없으므로 ready=false 로 응답해 프론트가 설치 안내를 띄운다.
 */
@Service
@Slf4j
public class UsageService {

    private static final Path USAGE_DIR =
            Paths.get(System.getProperty("user.home"), ".claude", "aidesk-usage");

    private final ObjectMapper objectMapper = new ObjectMapper();

    public LocalUsageRsVo getLocalUsage() {
        LocalUsageRsVo rs = new LocalUsageRsVo();

        if (!Files.isDirectory(USAGE_DIR)) return rs; // ready=false

        Path latest = findLatest(USAGE_DIR);
        if (latest == null) return rs;

        try {
            JsonNode root = objectMapper.readTree(Files.newInputStream(latest));
            rs.setReady(true);
            rs.setSource(latest.toString());
            rs.setFiveHourPct(asInt(root.path("fiveHourUsedPct"), -1));
            rs.setFiveHourResetsAt(asLong(root.path("fiveHourResetsAt"), 0));
            rs.setWeeklyPct(asInt(root.path("weeklyUsedPct"), -1));
            rs.setWeeklyResetsAt(asLong(root.path("weeklyResetsAt"), 0));
            // contextRemainingPct 은 "남은 %" 라 사용량으로 환산해 노출 (자동 압축 16.5% 마진은 무시).
            int rem = asInt(root.path("contextRemainingPct"), -1);
            if (rem >= 0) rs.setContextPct(Math.max(0, Math.min(100, 100 - rem)));
        } catch (IOException e) {
            log.warn("usage: read {} failed: {}", latest, e.getMessage());
        }

        return rs;
    }

    private Path findLatest(Path dir) {
        try (Stream<Path> stream = Files.list(dir)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".json"))
                    .max(Comparator.comparingLong(p -> p.toFile().lastModified()))
                    .orElse(null);
        } catch (IOException e) {
            log.warn("usage: list {} failed: {}", dir, e.getMessage());
            return null;
        }
    }

    private static int asInt(JsonNode n, int dflt) {
        if (n == null || n.isNull() || n.isMissingNode()) return dflt;
        return (int) Math.round(n.asDouble(dflt));
    }

    private static long asLong(JsonNode n, long dflt) {
        if (n == null || n.isNull() || n.isMissingNode()) return dflt;
        return n.asLong(dflt);
    }

    /**
     * ~/.claude/settings.json 에 statusLine 블록을 주입 (이미 있으면 교체).
     *
     * @return 0 = ok, 1 = 스크립트 파일 미발견, 2 = settings.json 갱신 실패
     */
    public int installStatuslineHook() {
        Path scriptPath = locateScript();
        if (scriptPath == null) return 1;

        Path settings = Paths.get(System.getProperty("user.home"), ".claude", "settings.json");
        try {
            Files.createDirectories(settings.getParent());
            Map<String, Object> root;
            if (Files.exists(settings) && Files.size(settings) > 0) {
                JsonNode existing = objectMapper.readTree(Files.newInputStream(settings));
                root = existing.isObject()
                        ? objectMapper.convertValue(existing, new com.fasterxml.jackson.core.type.TypeReference<>() {})
                        : new LinkedHashMap<>();
            } else {
                root = new LinkedHashMap<>();
            }

            Map<String, Object> statusLine = new LinkedHashMap<>();
            statusLine.put("type", "command");
            statusLine.put("command", "node \"" + scriptPath.toAbsolutePath() + "\"");
            root.put("statusLine", statusLine);

            byte[] pretty = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(root);
            Files.write(settings, pretty);
            log.info("usage: installed statusLine hook at {}", scriptPath);
            return 0;
        } catch (IOException e) {
            log.warn("usage: install hook failed: {}", e.getMessage());
            return 2;
        }
    }

    private Path locateScript() {
        // 백엔드 작업 디렉토리 기준으로 adesk-cli 위치를 추정.
        // 1) ./adesk-cli/bin/aidesk-statusline.js (모노레포 루트에서 기동된 경우)
        // 2) ../adesk-cli/bin/aidesk-statusline.js (backend/ 안에서 기동된 경우)
        Path cwd = Paths.get("").toAbsolutePath();
        Path[] candidates = new Path[] {
                cwd.resolve("adesk-cli/bin/aidesk-statusline.js"),
                cwd.resolve("../adesk-cli/bin/aidesk-statusline.js").normalize()
        };
        for (Path c : candidates) {
            if (Files.isRegularFile(c)) return c;
        }
        return null;
    }
}
