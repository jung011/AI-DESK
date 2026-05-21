package com.jsh.aidesk.serverapi.desktop.service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.desktop.vo.DesktopLocalInfoRqVo;
import com.jsh.aidesk.serverapi.desktop.vo.DesktopLocalInfoRsVo;
import com.jsh.aidesk.serverapi.desktop.vo.WorkspaceItemRqVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * Desktop Agent 가 보고한 로컬 스냅샷을 받아 t_ai_agent 의 status 를 갱신.
 *
 * 매칭 규칙: 보고된 워크스페이스의 workspaceDir 과 t_ai_agent.workspace_dir 의 문자열 동일성.
 *
 * 1단계 PoC: contextPct 는 변경하지 않는다 (statusline 이 별도로 기록). status 만 갱신.
 *
 * 옛 ownerEmployeeId 캐시는 케플릭스 ExternalAgentService 의 me 플래그용이었으나,
 * 자체 채널 모델 도입 후 폐기 — 본 service 는 status 갱신만 책임진다.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class DesktopService {

    private final AgentMapper agentMapper;

    public DesktopLocalInfoRsVo applyLocalInfo(DesktopLocalInfoRqVo req) {
        DesktopLocalInfoRsVo rs = new DesktopLocalInfoRsVo();
        if (req == null) return rs;

        List<WorkspaceItemRqVo> workspaces = req.getWorkspaces();
        rs.setTotalWorkspaces(workspaces == null ? 0 : workspaces.size());
        if (workspaces == null || workspaces.isEmpty()) return rs;

        // helper 가 보낸 reporter payload — 어느 user 의 mac 인지 모름 (helper-user binding 후속).
        // 본 단계에서는 *모든 user 의 에이전트* 를 대상으로 매칭 시도.
        List<AgentVo> agents = agentMapper.selectAllForSystem();
        Map<String, AgentVo> agentByWs = new HashMap<>();
        for (AgentVo a : agents) {
            if (a.getWorkspaceDir() != null && !a.getWorkspaceDir().isBlank()) {
                agentByWs.putIfAbsent(a.getWorkspaceDir(), a);
            }
        }

        int matched = 0;
        int updated = 0;
        for (WorkspaceItemRqVo w : workspaces) {
            if (w.getWorkspaceDir() == null || w.getStatus() == null) continue;
            AgentVo a = agentByWs.get(w.getWorkspaceDir());
            if (a == null) continue;
            matched++;
            if (!w.getStatus().equals(a.getStatus())) {
                agentMapper.updateStatusFromWatcher(a.getAgentId(), w.getStatus(), a.getContextPct());
                updated++;
                log.debug("desktop: agent={} status {} -> {} (from Helper)",
                        a.getAgentName(), a.getStatus(), w.getStatus());
            }
        }
        rs.setMatchedAgents(matched);
        rs.setUpdatedAgents(updated);
        log.debug("desktop.local-info: total={} matched={} updated={}",
                rs.getTotalWorkspaces(), matched, updated);
        return rs;
    }
}
