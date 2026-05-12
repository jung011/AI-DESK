package com.jsh.aidesk.serverapi.setting.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.setting.mapper.SettingMapper;

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
    /** (me) 에이전트는 tmux_session 으로 식별 — 워크스페이스가 바뀌어도 같은 행을 갱신. */
    private static final String ME_TMUX_PREFIX = "aidesk-self-";
    private static final String ME_MODEL = "claude-opus-4-7";

    private final SettingMapper mapper;
    private final AgentMapper agentMapper;
    private final ClaudeJsonScopeService claudeJsonScope;

    @Value("${kaflix.me-employee-id:}")
    private String meEmployeeId;

    /** A2A 워크스페이스 경로 — 없으면 빈 문자열 반환. */
    public String getA2aWorkspace() {
        String v = mapper.selectValue(KEY_A2A_WORKSPACE);
        return v == null ? "" : v;
    }

    /**
     * A2A 워크스페이스 변경. DB 저장 + `~/.claude.json` 의 kaflix-* MCP 스코프 이동 +
     * (me) 에이전트의 workspace_dir 동기화. 세 단계 모두 성공해야 정상 종료.
     *
     * @return rc 0=성공, 1=빈 경로, 2=경로 미존재/파일, 3=claude.json 갱신 실패
     */
    public int setA2aWorkspace(String path) {
        if (path == null || path.isBlank()) return 1;
        Path p = Paths.get(path);
        if (!Files.isDirectory(p)) {
            log.warn("setA2aWorkspace: 디렉토리 아님 path={}", path);
            return 2;
        }
        String absolute = p.toAbsolutePath().normalize().toString();

        String old = mapper.selectValue(KEY_A2A_WORKSPACE);
        try {
            claudeJsonScope.scopeKaflixToWorkspace(old, absolute);
        } catch (IOException | RuntimeException e) {
            log.warn("setA2aWorkspace: claude.json 갱신 실패 {}", e.getMessage());
            return 3;
        }
        mapper.upsertValue(KEY_A2A_WORKSPACE, absolute);
        upsertMeAgent(absolute);
        return 0;
    }

    /**
     * (me) 를 사무실 AI 그룹(t_ai_agent) 에 등록/갱신. 식별 키는 tmux_session
     * `aidesk-self-{employeeId}`. 사용자가 워크스페이스를 옮겨도 같은 row 가 따라간다.
     * meEmployeeId 가 비어 있으면 아무 일도 하지 않음.
     */
    private void upsertMeAgent(String workspaceDir) {
        if (meEmployeeId == null || meEmployeeId.isBlank()) {
            log.warn("upsertMeAgent: kaflix.me-employee-id 미설정 — 스킵");
            return;
        }
        String session = ME_TMUX_PREFIX + meEmployeeId.toLowerCase(Locale.ROOT);
        AgentVo existing = agentMapper.selectByTmuxSession(session);
        if (existing != null) {
            if (workspaceDir.equals(existing.getWorkspaceDir())) {
                log.info("upsertMeAgent: workspace 동일 — 갱신 불필요 (agentId={})", existing.getAgentId());
                return;
            }
            int n = agentMapper.updateWorkspaceDir(existing.getAgentId(), workspaceDir);
            log.info("upsertMeAgent: workspace 갱신 (agentId={}, updated={})", existing.getAgentId(), n);
            return;
        }
        AgentVo v = new AgentVo();
        v.setAgentId(UUID.randomUUID().toString());
        v.setAgentName(meEmployeeId + " (me)");
        v.setWorkspaceDir(workspaceDir);
        v.setTmuxSession(session);
        v.setStatus("active");
        v.setModel(ME_MODEL);
        agentMapper.insert(v);
        log.info("upsertMeAgent: 신규 (me) 에이전트 등록 agentId={}", v.getAgentId());
    }
}
