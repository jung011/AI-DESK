package com.jsh.aidesk.serverapi.setting.service;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.util.Locale;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.setting.mapper.SettingMapper;
import com.jsh.aidesk.serverapi.setting.vo.CodeServerRsVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 런타임 변경 가능한 단일값 앱 설정.
 *
 * 현재 다루는 키:
 *   - `a2a_workspace` : 사내 동료 AI 와의 소통(kaflix-a2a/kaflix-channel) 권한이 활성화될
 *     워크스페이스 절대 경로. 미설정 시 (me) 터미널 열기는 비활성.
 *
 * 부수효과: 워크스페이스 변경 시 (me) 자신을 사무실 AI 그룹(`t_ai_agent`) 에도 upsert
 * 한다. 그래야 사무실 내부 AI 들이 aidesk-channel.send_to 로 (me) 와 양방향 소통 가능.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class SettingService {

    public static final String KEY_A2A_WORKSPACE = "a2a_workspace";
    /** 신규 AI 부트스트랩 시 읽힐 작업 규칙 문서의 절대 경로. Helper 가 이 경로를 기반으로
     *  프롬프트 ("먼저 {path} 를 읽고...") 를 만들어 claude 에 자동 주입한다. 미설정이면 주입 생략. */
    public static final String KEY_WORKROLE_FILE = "workrole_file";
    /** (me) 에이전트는 tmux_session 으로 식별 — 워크스페이스가 바뀌어도 같은 행을 갱신. */
    private static final String ME_TMUX_PREFIX = "aidesk-self-";
    private static final String ME_MODEL = "claude-opus-4-7";

    private final SettingMapper mapper;
    private final AgentMapper agentMapper;

    @Value("${vscode.code-server-url:}")
    private String codeServerUrl;

    /** A2A 워크스페이스 경로 — 없으면 빈 문자열 반환. 본인 user 의 설정만. */
    public String getA2aWorkspace() {
        Long me = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentAccountSn();
        String v = mapper.selectValue(me, KEY_A2A_WORKSPACE);
        return v == null ? "" : v;
    }

    /** 작업 규칙 문서 파일 경로 — 본인 user 의 설정만. */
    public String getWorkroleFile() {
        Long me = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentAccountSn();
        String v = mapper.selectValue(me, KEY_WORKROLE_FILE);
        return v == null ? "" : v;
    }

    /** 작업 규칙 문서 파일 경로 저장. */
    public void setWorkroleFile(String path) {
        Long me = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentAccountSn();
        mapper.upsertValue(me, KEY_WORKROLE_FILE, path == null ? "" : path);
    }

    /**
     * 임베드용 code-server URL + 현재 살아있는지 alive 플래그.
     * Java HTTP 클라이언트가 code-server 의 비표준 응답을 종종 잘못 파싱하므로,
     * "포트가 열려 있는가" 만 단순 TCP 연결로 판정한다 — iframe 자체는 브라우저가 직접 띄우니
     * 정확한 HTTP 코드 검증까지는 불필요.
     */
    public CodeServerRsVo getCodeServer() {
        String url = codeServerUrl == null ? "" : codeServerUrl.trim();
        if (url.isEmpty()) return new CodeServerRsVo("", false);
        boolean alive = false;
        try {
            URI uri = URI.create(url);
            int port = uri.getPort();
            if (port < 0) port = "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
            String host = uri.getHost() == null ? "localhost" : uri.getHost();
            try (Socket s = new Socket()) {
                s.connect(new InetSocketAddress(host, port), 700);
                alive = true;
            }
        } catch (IOException | IllegalArgumentException e) {
            log.debug("code-server probe failed: url={} err={}", url, e.getMessage());
        }
        return new CodeServerRsVo(url, alive);
    }

    /**
     * A2A 워크스페이스 저장.
     *
     * 호스트 폴더 검증 + `~/.claude.json` scope 처리는 frontend 가 *본인 mac 의*
     * Helper /api/scope-workspace 를 직접 호출하여 끝낸 뒤 절대 경로를 이 endpoint
     * 로 넘긴다. 백엔드는 그 경로를 신뢰하고 DB upsert + (me) row 만 처리한다.
     * (옛 흐름: 백엔드 → host.docker.internal:30083 호출은 *백엔드가 도는 mac 의*
     * helper 만 가리키므로 다른 mac 사용자에겐 동작하지 않았음.)
     *
     * @return rc 0=성공, 1=빈 경로
     */
    public int setA2aWorkspace(String path, boolean purgePreviousHistory) {
        if (path == null || path.isBlank()) return 1;

        Long me = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentAccountSn();
        String meLoginId = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentLoginId();
        String employeeKey = deriveEmployeeKey(meLoginId);
        mapper.upsertValue(me, KEY_A2A_WORKSPACE, path);
        upsertMeAgent(path, me, employeeKey);
        return 0;
    }

    /**
     * login_id 에서 (me) tmux_session 의 employee key 부분 추출.
     * 예: "liki@kaflix.com" → "liki", "wood" → "wood".
     * 옛 kaflix.me-employee-id 의존 제거.
     */
    private static String deriveEmployeeKey(String loginId) {
        if (loginId == null) return "";
        String head = loginId.trim().toLowerCase(Locale.ROOT);
        int at = head.indexOf('@');
        if (at > 0) head = head.substring(0, at);
        // tmux session 호환 문자만 (영숫자, -, _)
        return head.replaceAll("[^a-z0-9_-]", "");
    }

    /**
     * (me) 를 사무실 AI 그룹(t_ai_agent) 에 등록/갱신. 식별 키는 tmux_session
     * `aidesk-self-{employeeId}`. 사용자가 워크스페이스를 옮겨도 같은 row 가 따라간다.
     * meEmployeeId 가 비어 있으면 아무 일도 하지 않음.
     */
    private void upsertMeAgent(String workspaceDir, Long ownerAccountSn, String employeeKey) {
        if (employeeKey == null || employeeKey.isEmpty()) {
            log.warn("upsertMeAgent: employee key 추출 실패 — 스킵");
            return;
        }
        String session = ME_TMUX_PREFIX + employeeKey;
        AgentVo existing = agentMapper.selectByTmuxSession(session);
        if (existing != null) {
            if (workspaceDir.equals(existing.getWorkspaceDir())) {
                log.info("upsertMeAgent: workspace 동일 — 갱신 불필요 (agentId={})", existing.getAgentId());
                return;
            }
            int n = agentMapper.updateWorkspaceDir(existing.getAgentId(), workspaceDir, ownerAccountSn);
            log.info("upsertMeAgent: workspace 갱신 (agentId={}, updated={})", existing.getAgentId(), n);
            return;
        }
        AgentVo v = new AgentVo();
        v.setAgentId(UUID.randomUUID().toString());
        v.setOwnerAccountSn(ownerAccountSn);
        v.setAgentName(employeeKey + " (me)");
        v.setWorkspaceDir(workspaceDir);
        v.setTmuxSession(session);
        v.setStatus("active");
        v.setModel(ME_MODEL);
        agentMapper.insert(v);
        log.info("upsertMeAgent: 신규 (me) 에이전트 등록 agentId={}", v.getAgentId());
    }
}
