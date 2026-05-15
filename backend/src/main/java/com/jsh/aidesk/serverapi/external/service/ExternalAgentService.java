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
import com.jsh.aidesk.serverapi.desktop.service.DesktopService;
import com.jsh.aidesk.serverapi.external.vo.ExternalAgentRsVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 사내 kaflix-a2a Control Plane 에서 외부 직원 에이전트 목록을 가져온다.
 *
 * - 엔드포인트: `${kaflix.control-plane-url}/v1/agents/lite` (인증 불필요)
 * - 호출 실패 / CP 미가동 시 빈 목록 반환 — 대시보드가 깨지지 않도록 graceful.
 * - 5초 타임아웃.
 *
 * (me) 마킹은 desktop-agent(Python Helper) 가 보고한 ownerEmployeeId 를 우선 사용하고,
 * 보고가 없을 때만 application.yaml 의 me-employee-id 로 fallback 한다. 사용자별 환경
 * 설정 없이도 각자의 PC 에서 자기 카드가 (me) 로 표시된다.
 *
 * 본인 터미널 열기 등 macOS-종속 동작은 desktop-agent 가 처리하므로 본 서비스에선 제거됨.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class ExternalAgentService {

    private static final TypeReference<List<JsonNode>> LIST_TYPE = new TypeReference<>() {};

    @Value("${kaflix.control-plane-url:}")
    private String controlPlaneUrl;

    @Value("${kaflix.me-employee-id:}")
    private String meEmployeeId;

    private final DesktopService desktopService;

    private final ObjectMapper mapper = new ObjectMapper();

    /**
     * me 결정 우선순위:
     *   1) Helper 가 보고한 ownerEmployeeId (kaflix-a2a 사이드카에서 추출, 자동)
     *   2) application.yaml 의 kaflix.me-employee-id (fallback, 정적 config)
     */
    private String resolveMeEmployeeId() {
        String reported = desktopService.getReportedOwnerEmployeeId();
        if (reported != null && !reported.isBlank()) return reported;
        return meEmployeeId;
    }

    public List<ExternalAgentRsVo> list() {
        if (controlPlaneUrl == null || controlPlaneUrl.isBlank()) {
            return Collections.emptyList();
        }
        String url = controlPlaneUrl.replaceAll("/$", "") + "/v1/agents/lite";
        try {
            // Spring 컨텍스트의 long-lived HttpClient 인스턴스가 네트워크 변경(Mac sleep/wake 등)
            // 이후 "No route to host" 에 갇히는 케이스를 회피하기 위해 매 호출마다 새 클라이언트를
            // 사용한다. low-frequency 폴링(대시보드 30s 간격) 이라 비용은 무시 가능.
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest req = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<String> res = client.send(req, HttpResponse.BodyHandlers.ofString());
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
        String me = resolveMeEmployeeId();
        v.setMe(!v.getEmployeeId().isBlank()
                && me != null
                && v.getEmployeeId().equalsIgnoreCase(me));
        return v;
    }
}
