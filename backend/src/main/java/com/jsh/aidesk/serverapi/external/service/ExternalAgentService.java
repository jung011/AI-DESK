package com.jsh.aidesk.serverapi.external.service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jsh.aidesk.serverapi.external.vo.ExternalAgentRsVo;

import lombok.extern.slf4j.Slf4j;

/**
 * 사내 kaflix-a2a Control Plane 에서 외부 직원 에이전트 목록을 가져온다.
 *
 * - 엔드포인트: `${kaflix.control-plane-url}/v1/agents/lite` (인증 불필요)
 * - 호출 실패 / CP 미가동 시 빈 목록 반환 — 대시보드가 깨지지 않도록 graceful.
 * - 5초 타임아웃.
 */
@Service
@Slf4j
public class ExternalAgentService {

    private static final TypeReference<List<JsonNode>> LIST_TYPE = new TypeReference<>() {};

    @Value("${kaflix.control-plane-url:}")
    private String controlPlaneUrl;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();
    private final ObjectMapper mapper = new ObjectMapper();

    public List<ExternalAgentRsVo> list() {
        if (controlPlaneUrl == null || controlPlaneUrl.isBlank()) {
            return Collections.emptyList();
        }
        String url = controlPlaneUrl.replaceAll("/$", "") + "/v1/agents/lite";
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() != 200) {
                log.warn("external agents fetch failed: status={} url={}", res.statusCode(), url);
                return Collections.emptyList();
            }
            List<JsonNode> raw = mapper.readValue(res.body(), LIST_TYPE);
            return raw.stream().map(this::toVo).toList();
        } catch (Exception e) {
            log.warn("external agents fetch error url={} err={}", url, e.getMessage());
            return Collections.emptyList();
        }
    }

    private ExternalAgentRsVo toVo(JsonNode n) {
        ExternalAgentRsVo v = new ExternalAgentRsVo();
        v.setEmployeeId(n.path("employeeId").asText(""));
        v.setName(n.path("name").asText(v.getEmployeeId()));
        v.setDepartment(n.path("department").asText(""));
        v.setOnline(n.path("online").asBoolean(false));
        List<String> skills = new ArrayList<>();
        JsonNode arr = n.path("skills");
        if (arr.isArray()) {
            arr.forEach(s -> skills.add(s.asText("")));
        }
        v.setSkills(skills);
        return v;
    }
}
