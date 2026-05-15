package com.jsh.aidesk.serverapi.external.service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jsh.aidesk.serverapi.desktop.service.DesktopService;
import com.jsh.aidesk.serverapi.external.vo.ExternalAgentRsVo;
import com.jsh.aidesk.serverapi.setting.service.SettingService;

import lombok.RequiredArgsConstructor;
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
@RequiredArgsConstructor
public class ExternalAgentService {

    private static final TypeReference<List<JsonNode>> LIST_TYPE = new TypeReference<>() {};

    @Value("${kaflix.control-plane-url:}")
    private String controlPlaneUrl;

    @Value("${kaflix.me-employee-id:}")
    private String meEmployeeId;

    private final SettingService settingService;
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

    /**
     * 본인의 AI Desk 터미널을 띄운다 — 여기서 kaflix-a2a 도구로 사내 동료들과 소통한다.
     * 본인(me) 만 허용 — 동료 카드에서는 호출되지 않는다 (프론트에서 버튼이 me 일 때만 노출).
     *
     * 동작:
     *   - 워크스페이스: `kaflix.colleague-terminal-workspace` (kaflix-a2a/kaflix-channel MCP 권한이
     *     활성화된 디렉토리여야 함)
     *   - tmux 세션: `aidesk-self-{employeeId}` — 반복 클릭해도 윈도우 1개
     *   - 명령: `claude -c` 로 기존 대화를 이어 받음
     *   - 컨텍스트 프롬프트는 따로 주입하지 않는다 — 본인이 직접 무엇을 할지 입력
     *
     * @return 0 = 성공, 1 = 잘못된 employeeId / 본인 아님, 2 = 워크스페이스 미설정, 3 = OS 미지원, 4 = 실행 실패
     */
    public int openTerminal(String employeeId) {
        if (employeeId == null || employeeId.isBlank()) return 1;
        if (!employeeId.equalsIgnoreCase(meEmployeeId)) return 1;

        String dir = settingService.getA2aWorkspace();
        if (dir == null || dir.isBlank()) return 2;

        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (!os.contains("mac")) {
            log.warn("openMyTerminal: unsupported OS '{}'", os);
            return 3;
        }

        String session = "aidesk-self-" + employeeId.toLowerCase(Locale.ROOT);
        String displayName = resolveDisplayName(employeeId);

        String dirEsc = dir.replace("\\", "\\\\").replace("\"", "\\\"");
        String titleEsc = (displayName + " (me)")
                .replace("\\", "\\\\").replace("\"", "\\\"");
        String script = ""
                + "set sessionName to \"" + session + "\"\n"
                + "set wsQuoted to quoted form of \"" + dirEsc + "\"\n"
                + "set tabTitle to \"" + titleEsc + "\"\n"
                // 끝에 `; exit 0` — tmux 가 끝나면 부모 zsh 도 exit 0 으로 같이 종료되도록.
                // (Terminal 기본 프로필이 셸 정상 종료 시 윈도우를 자동으로 닫는다)
                + "set shellCmd to \"cd \" & wsQuoted & \" && tmux new-session -A -s \" & sessionName & \" 'claude -c'; exit 0\"\n"
                + "set termRunning to false\n"
                + "try\n"
                + "  do shell script \"pgrep -x Terminal > /dev/null\"\n"
                + "  set termRunning to true\n"
                + "end try\n"
                + "set clientTty to \"\"\n"
                + "try\n"
                + "  set clientTty to do shell script \"tmux list-clients -t \" & sessionName & \" -F '#{client_tty}' 2>/dev/null | head -n 1\"\n"
                + "end try\n"
                + "if clientTty is not \"\" then\n"
                + "  tell application \"Terminal\"\n"
                + "    activate\n"
                + "    repeat with w in windows\n"
                + "      repeat with t in tabs of w\n"
                + "        try\n"
                + "          if (tty of t) is clientTty then\n"
                + "            set frontmost of w to true\n"
                + "            set selected of t to true\n"
                + "            return\n"
                + "          end if\n"
                + "        end try\n"
                + "      end repeat\n"
                + "    end repeat\n"
                + "  end tell\n"
                + "end if\n"
                + "if termRunning then\n"
                + "  tell application \"Terminal\"\n"
                + "    activate\n"
                + "    set newTab to do script shellCmd\n"
                + "    try\n"
                + "      set font size of newTab to 14\n"
                + "    end try\n"
                + "    try\n"
                + "      set custom title of newTab to tabTitle\n"
                + "    end try\n"
                + "  end tell\n"
                + "else\n"
                + "  tell application \"Terminal\"\n"
                + "    launch\n"
                + "    repeat 30 times\n"
                + "      if (count windows) > 0 then exit repeat\n"
                + "      delay 0.1\n"
                + "    end repeat\n"
                + "    activate\n"
                + "    if (count windows) > 0 then\n"
                + "      set newTab to do script shellCmd in selected tab of front window\n"
                + "    else\n"
                + "      set newTab to do script shellCmd\n"
                + "    end if\n"
                + "    try\n"
                + "      set font size of newTab to 14\n"
                + "    end try\n"
                + "    try\n"
                + "      set custom title of newTab to tabTitle\n"
                + "    end try\n"
                + "  end tell\n"
                + "end if\n";

        try {
            new ProcessBuilder("osascript", "-e", script).start();
            log.info("openMyTerminal: employeeId={} session={} dir={}", employeeId, session, dir);
            return 0;
        } catch (IOException e) {
            log.warn("openMyTerminal failed: {}", e.getMessage());
            return 4;
        }
    }

    /** Control Plane 응답에서 표시명을 다시 한 번 조회 (대상 employeeId 가 사라졌으면 빈 문자열). */
    private String resolveDisplayName(String employeeId) {
        for (ExternalAgentRsVo v : list()) {
            if (employeeId.equalsIgnoreCase(v.getEmployeeId())) {
                return v.getName() == null || v.getName().isBlank() ? employeeId : v.getName();
            }
        }
        return employeeId;
    }
}
