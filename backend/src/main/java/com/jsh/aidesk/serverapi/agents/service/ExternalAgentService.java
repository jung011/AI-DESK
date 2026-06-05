package com.jsh.aidesk.serverapi.agents.service;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.util.BearerTokenUtil;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.agents.vo.ExternalAgentCreateRqVo;
import com.jsh.aidesk.serverapi.agents.vo.ExternalAgentTokenRsVo;
import com.jsh.aidesk.serverapi.common.jwt.AuthContext;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 외부 AI agent CRUD + Bearer token 발급/rotate/revoke.
 *
 * <p>외부 AI 의 책임 범위는 통신 채널뿐 — workrole/identity/운영은 외부 AI 자체.
 * 따라서 본 service 가 다루는 건 (1) agent row 생성 / (2) token lifecycle 만.
 *
 * <p>workspace_dir / tmux_session / model 은 internal AI 와 schema 를 공유하기 위해
 * placeholder 값으로 채운다 (NOT NULL 제약 + uq_ai_agent_tmux_session 충돌 회피).
 *
 * <p>Token raw 는 발급/rotate 시점 1회만 호출자에게 반환되고 그 이후엔 어디서도 복원
 * 불가 — DB 에는 SHA-256 hash 만.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ExternalAgentService {

    /** 외부 AI 의 placeholder model 값 — internal AI 의 claude-opus-* 와 구분. */
    public static final String EXTERNAL_MODEL_PLACEHOLDER = "external";
    /** 외부 AI 의 placeholder workspace — UI 표시용. */
    public static final String EXTERNAL_WORKSPACE_PLACEHOLDER = "(external)";

    private final AgentMapper agentMapper;
    private final BearerTokenUtil tokenUtil;

    /** 외부 AI 신규 등록 + 초기 Bearer token 발급. response 의 token 은 1회만 노출. */
    @Transactional
    public ExternalAgentTokenRsVo create(ExternalAgentCreateRqVo req) {
        Long me = AuthContext.currentAccountSn();
        String name = req.getAgentName() == null ? "" : req.getAgentName().trim();
        if (name.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "agentName is required");
        }

        AgentVo agent = new AgentVo();
        String agentId = UUID.randomUUID().toString();
        agent.setAgentId(agentId);
        agent.setOwnerAccountSn(me);
        agent.setAgentName(name);
        // placeholder — schema NOT NULL 제약 + uq_ai_agent_tmux_session 충돌 회피. tmux 는 실제 없음.
        agent.setWorkspaceDir(EXTERNAL_WORKSPACE_PLACEHOLDER);
        agent.setTmuxSession("external-" + agentId);
        agent.setStatus("offline");                         // ws connect 전까지 offline. connect 시 idle.
        agent.setModel(EXTERNAL_MODEL_PLACEHOLDER);

        String rawToken = tokenUtil.generateRawToken();
        agent.setBearerTokenHash(tokenUtil.hash(rawToken));

        agentMapper.insertExternal(agent);
        log.info("[external-agent] created agentId={} name={} owner={}", agentId, name, me);

        return new ExternalAgentTokenRsVo(agentId, name, rawToken);
    }

    /** Token rotate — 기존 hash 무효화 + 새 raw token 1회 반환. */
    @Transactional
    public ExternalAgentTokenRsVo rotateToken(String agentId) {
        Long me = AuthContext.currentAccountSn();
        AgentVo current = agentMapper.selectById(agentId, me);
        if (current == null || !"external".equals(current.getAgentType())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "external agent not found or not yours");
        }
        String rawToken = tokenUtil.generateRawToken();
        int updated = agentMapper.updateBearerToken(agentId, me, tokenUtil.hash(rawToken));
        if (updated == 0) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "rotate failed");
        }
        log.info("[external-agent] token rotated agentId={} owner={}", agentId, me);
        return new ExternalAgentTokenRsVo(agentId, current.getAgentName(), rawToken);
    }

    /** Token revoke — hash NULL. 외부 AI 는 이후 인증 실패. */
    @Transactional
    public void revokeToken(String agentId) {
        Long me = AuthContext.currentAccountSn();
        AgentVo current = agentMapper.selectById(agentId, me);
        if (current == null || !"external".equals(current.getAgentType())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "external agent not found or not yours");
        }
        agentMapper.revokeBearerToken(agentId, me);
        log.info("[external-agent] token revoked agentId={} owner={}", agentId, me);
    }
}
