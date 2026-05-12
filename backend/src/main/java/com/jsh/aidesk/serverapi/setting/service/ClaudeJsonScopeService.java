package com.jsh.aidesk.serverapi.setting.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.node.ObjectNode;

import lombok.extern.slf4j.Slf4j;

/**
 * `~/.claude.json` 에 등록된 MCP 서버의 스코프를 조정한다.
 *
 * 정책상 `kaflix-a2a` / `kaflix-channel` 두 MCP 서버는 (me) 사용자가 지정한
 * 단일 워크스페이스에서만 사용 가능해야 한다. AI 사무실 내부 AI(코드검증/리본API/셔틀 등)
 * 들은 자기 cwd 에 그 서버 등록이 없어 도구 자체가 노출되지 않는다.
 *
 * 이 서비스는:
 *   1) 글로벌 (top-level) mcpServers 에 위 두 서버가 있으면 제거하고 정의를 회수,
 *   2) 이전에 사용하던 워크스페이스 (`projects.<old>.mcpServers`) 에서도 회수,
 *   3) 새 워크스페이스 (`projects.<new>.mcpServers`) 에 등록한다.
 *
 * 동시쓰기/손상 방지: 매 호출마다 `.bak-YYYYMMDD-HHmmss` 백업 → 같은 디렉토리 임시
 * 파일 작성 → ATOMIC_MOVE 로 교체.
 */
@Service
@Slf4j
public class ClaudeJsonScopeService {

    private static final List<String> SCOPED_SERVERS = List.of("kaflix-a2a", "kaflix-channel");
    private static final DateTimeFormatter STAMP =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");

    private final ObjectMapper mapper = new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT);

    private Path claudeJsonPath() {
        return Paths.get(System.getProperty("user.home"), ".claude.json");
    }

    /**
     * `kaflix-a2a` / `kaflix-channel` MCP 등록을 newWorkspace 로 이전한다.
     *
     * @param oldWorkspace 직전 워크스페이스 경로 (없으면 null/빈)
     * @param newWorkspace 새로 지정할 워크스페이스 경로 (필수)
     */
    public void scopeKaflixToWorkspace(String oldWorkspace, String newWorkspace) throws IOException {
        if (newWorkspace == null || newWorkspace.isBlank()) {
            throw new IllegalArgumentException("newWorkspace 가 비어 있습니다.");
        }
        Path file = claudeJsonPath();
        if (!Files.exists(file)) {
            throw new IOException("~/.claude.json 이 존재하지 않습니다: " + file);
        }

        backup(file);

        ObjectNode root = (ObjectNode) mapper.readTree(file.toFile());

        // 1) 글로벌 mcpServers 에서 회수 — 정의를 보존 (target 에 옮기기 위해)
        Map<String, JsonNode> harvested = new java.util.LinkedHashMap<>();
        JsonNode topServersNode = root.get("mcpServers");
        if (topServersNode instanceof ObjectNode topServers) {
            for (String name : SCOPED_SERVERS) {
                JsonNode v = topServers.remove(name);
                if (v != null) harvested.put(name, v);
            }
        }

        // 2) 이전 워크스페이스에서 회수 (oldWorkspace 가 있고 newWorkspace 와 다른 경우)
        if (oldWorkspace != null && !oldWorkspace.isBlank()
                && !oldWorkspace.equals(newWorkspace)) {
            JsonNode oldEntry = projectEntry(root, oldWorkspace, false);
            if (oldEntry instanceof ObjectNode oldObj) {
                JsonNode servers = oldObj.get("mcpServers");
                if (servers instanceof ObjectNode oldServers) {
                    for (String name : SCOPED_SERVERS) {
                        JsonNode v = oldServers.remove(name);
                        if (v != null && !harvested.containsKey(name)) {
                            harvested.put(name, v);
                        }
                    }
                }
            }
        }

        // 3) 새 워크스페이스에 등록 — 정의가 회수되지 않았더라도 빈 객체로 등록하지는 않음.
        //    (이전 글로벌·과거 워크스페이스 어느 쪽에도 정의가 없는 경우는 사용자 환경 이상으로
        //    간주하고 경고만 남긴다.)
        if (harvested.isEmpty()) {
            log.warn("scopeKaflixToWorkspace: 회수된 MCP 정의가 없어 새 워크스페이스에도 등록하지 않습니다."
                    + " 글로벌·과거 워크스페이스 모두에 {} 가 없었음.", SCOPED_SERVERS);
        } else {
            ObjectNode newEntry = (ObjectNode) projectEntry(root, newWorkspace, true);
            ObjectNode newServers = (ObjectNode) newEntry.get("mcpServers");
            if (newServers == null) {
                newServers = newEntry.putObject("mcpServers");
            }
            for (Map.Entry<String, JsonNode> e : harvested.entrySet()) {
                newServers.set(e.getKey(), e.getValue());
            }
        }

        // 4) 임시 파일에 쓰고 atomic move
        Path tmp = Files.createTempFile(file.getParent(), ".claude-aidesk-", ".tmp");
        try {
            mapper.writeValue(tmp.toFile(), root);
            Files.move(tmp, file, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            log.info("scopeKaflixToWorkspace: {} → {} (회수 {} 건)", oldWorkspace, newWorkspace, harvested.size());
        } finally {
            Files.deleteIfExists(tmp);
        }
    }

    /** projects.<path> 항목을 조회 (createIfAbsent=true 면 없으면 새로 만든다). */
    private JsonNode projectEntry(ObjectNode root, String workspacePath, boolean createIfAbsent) {
        ObjectNode projects = (ObjectNode) root.get("projects");
        if (projects == null) {
            if (!createIfAbsent) return null;
            projects = root.putObject("projects");
        }
        // Jackson 의 path() 는 분절 키를 인식하지만, projects 의 키는 "/Users/..." 절대경로라
        // 점/슬래시가 섞여 들어가는 경우가 있어 get/set 으로 명시적으로 다룬다.
        JsonNode entry = projects.get(workspacePath);
        if (entry == null) {
            if (!createIfAbsent) return null;
            entry = projects.putObject(workspacePath);
        }
        return entry;
    }

    /** 단순한 타임스탬프 백업: ~/.claude.json.bak-yyyyMMdd-HHmmss */
    private void backup(Path file) throws IOException {
        String stamp = LocalDateTime.now().format(STAMP);
        Path bak = file.resolveSibling(file.getFileName().toString() + ".bak-" + stamp);
        Files.copy(file, bak, StandardCopyOption.REPLACE_EXISTING);
        log.info("backed up {} -> {}", file, bak);
        pruneOldBackups(file, 5);
    }

    /** 같은 prefix 의 백업이 N 개를 넘으면 오래된 것부터 삭제. */
    private void pruneOldBackups(Path file, int keep) {
        String prefix = file.getFileName().toString() + ".bak-";
        try (var stream = Files.list(file.getParent())) {
            List<Path> baks = stream
                    .filter(p -> p.getFileName().toString().startsWith(prefix))
                    .sorted()
                    .toList();
            int toDelete = baks.size() - keep;
            if (toDelete <= 0) return;
            Iterator<Path> it = baks.iterator();
            for (int i = 0; i < toDelete && it.hasNext(); i++) {
                Path old = it.next();
                Files.deleteIfExists(old);
                log.info("pruned old backup {}", old);
            }
        } catch (IOException e) {
            log.warn("backup prune failed: {}", e.getMessage());
        }
    }

}
