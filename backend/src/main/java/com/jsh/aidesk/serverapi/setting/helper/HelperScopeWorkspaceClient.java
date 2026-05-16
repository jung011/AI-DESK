package com.jsh.aidesk.serverapi.setting.helper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import lombok.extern.slf4j.Slf4j;

/**
 * Helper(데스크톱 앱) 의 `/api/scope-workspace` 호출 — A2A 워크스페이스 검증 및
 * `~/.claude.json` 의 kaflix-* MCP scope 이동 위임.
 *
 * 백엔드가 도커 컨테이너에서 동작하므로 호스트 파일시스템에 접근 가능한 Helper 가 담당.
 * tmux preflight 와 달리 실제 작업 위임이므로 fail-open 안 됨 — Helper 응답 실패 시
 * 그대로 에러 전파.
 */
@Component
@Slf4j
public class HelperScopeWorkspaceClient {

    private static final String DEFAULT_HELPER_URL = "http://host.docker.internal:30083";

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();
    private final ObjectMapper mapper = new ObjectMapper();

    @Value("${aidesk.helper-url:}")
    private String configuredHelperUrl;

    public record Result(int rc, String message, String absolutePath) {}

    /**
     * @param newWorkspace 새 워크스페이스 경로 (호스트 절대 경로 권장)
     * @param oldWorkspace 직전 워크스페이스 경로 (없으면 null/빈)
     * @param purgePreviousHistory 옛 + 새 워크스페이스의 jsonl 대화 기록 삭제 + (me) tmux 세션 kill.
     *                             claude --resume 으로 옛 대화 복원되는 케이스 끊기용.
     * @param meTmuxSession (me) tmux 세션 이름 (purge 시 kill 대상). 없으면 null/빈.
     * @return rc=0 성공 / 1 빈 경로 / 2 디렉토리 아님 / 3 claude.json 처리 실패 / 9 helper 통신 실패
     */
    public Result scope(String newWorkspace, String oldWorkspace,
                        boolean purgePreviousHistory, String meTmuxSession) {
        if (newWorkspace == null || newWorkspace.isBlank()) {
            return new Result(1, "newWorkspace 가 비어 있습니다.", "");
        }
        String url = resolveHelperUrl() + "/api/scope-workspace";
        ObjectNode body = mapper.createObjectNode();
        body.put("newWorkspace", newWorkspace);
        body.put("oldWorkspace", oldWorkspace == null ? "" : oldWorkspace);
        body.put("purgePreviousHistory", purgePreviousHistory);
        body.put("meTmuxSession", meTmuxSession == null ? "" : meTmuxSession);
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
            JsonNode node = mapper.readTree(res.body());
            int rc = node.path("rc").asInt(9);
            String message = node.path("message").asText("");
            String absolutePath = node.path("absolutePath").asText("");
            if (res.statusCode() / 100 != 2 && rc == 0) {
                // helper 가 rc=0 인데 HTTP non-2xx 인 비정상 케이스
                log.warn("scope-workspace: helper non-2xx but rc=0 status={} body={}",
                        res.statusCode(), res.body());
            }
            return new Result(rc, message, absolutePath);
        } catch (Exception e) {
            log.warn("scope-workspace: helper unreachable url={} err={}", url, e.getMessage());
            return new Result(9, "Helper 와 통신할 수 없습니다: " + e.getMessage(), "");
        }
    }

    private String resolveHelperUrl() {
        return (configuredHelperUrl == null || configuredHelperUrl.isBlank())
                ? DEFAULT_HELPER_URL
                : configuredHelperUrl.replaceAll("/$", "");
    }
}
