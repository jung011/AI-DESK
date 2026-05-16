package com.jsh.aidesk.serverapi.messages.preflight;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import lombok.extern.slf4j.Slf4j;

/**
 * Helper(데스크톱 앱) 의 `/api/check-tmux` 를 호출해 수신 AI 의 tmux 세션이 호스트에
 * 실제로 살아있는지 확인. 메시지 발신 pre-flight 에 사용.
 *
 * Helper 가 다운/타임아웃 등으로 응답 못 받으면 conservative 하게 "alive=true, reason='helper unreachable'"
 * 로 통과시킴 — Helper 자체 장애가 메시지 발신을 전면 차단하면 안 됨.
 */
@Component
@Slf4j
public class HelperTmuxChecker {

    private static final String DEFAULT_HELPER_URL = "http://host.docker.internal:30083";

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(800))
            .build();
    private final ObjectMapper mapper = new ObjectMapper();

    @Value("${aidesk.helper-url:}")
    private String configuredHelperUrl;

    public record Result(boolean alive, String reason) {}

    public Result check(String tmuxSession) {
        if (tmuxSession == null || tmuxSession.isBlank()) {
            return new Result(false, "tmux_session 미설정");
        }
        String url = resolveHelperUrl() + "/api/check-tmux";
        String body = "{\"tmuxSession\":\"" + tmuxSession.replace("\"", "\\\"") + "\"}";
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofMillis(1500))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() / 100 != 2) {
                log.warn("preflight: helper /api/check-tmux non-2xx status={} body={}",
                        res.statusCode(), res.body());
                return new Result(true, "helper non-2xx — assume alive");
            }
            JsonNode node = mapper.readTree(res.body());
            boolean alive = node.path("alive").asBoolean(false);
            String reason = node.path("reason").asText("");
            return new Result(alive, reason);
        } catch (Exception e) {
            log.warn("preflight: helper unreachable url={} err={}", url, e.getMessage());
            // fail-open: helper 자체 문제로 발신 전체 차단되면 안 됨.
            return new Result(true, "helper unreachable — assume alive");
        }
    }

    private String resolveHelperUrl() {
        return (configuredHelperUrl == null || configuredHelperUrl.isBlank())
                ? DEFAULT_HELPER_URL
                : configuredHelperUrl.replaceAll("/$", "");
    }
}
