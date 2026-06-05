package com.jsh.aidesk.serverapi.messages.websocket;

import java.util.Map;

import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.util.BearerTokenUtil;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.common.jwt.AuthenticatedUser;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * WebSocket handshake 인증 — 세 경로 허용:
 *   1. cookie JWT 가 SecurityContext 에 AuthenticatedUser 를 세팅한 경우 (브라우저 chat UI)
 *   2. ?agentId=<UUID> query — t_ai_agent 에서 owner 를 찾아 fallback (내부 봇 어댑터)
 *   3. ?token=aidesk_ext_... query — Bearer token 으로 외부 AI 인증 (Phase 2)
 *
 * (2) 는 사내 망 + cross-account isolation 으로 안전. (3) 은 외부 환경 노출 대비 —
 * 외부 AI 가 ws connect 시 표준 Authorization 헤더는 브라우저/봇 어댑터 제약상 query 로 옮김.
 *
 * 인증 통과 시 attributes 에:
 *   ATTR_ACCOUNT_SN — owner account_sn
 *   ATTR_AGENT_ID   — 봇 어댑터 / 외부 AI 의 agent_id (cookie JWT 만 통과 시엔 미설정)
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class JwtHandshakeInterceptor implements HandshakeInterceptor {

    private final AgentMapper agentMapper;
    private final BearerTokenUtil tokenUtil;

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                    WebSocketHandler wsHandler, Map<String, Object> attributes) {
        // 1) cookie JWT 인증
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof AuthenticatedUser user) {
            attributes.put(MessageWebSocketHandler.ATTR_ACCOUNT_SN, user.getAccountSn());
            return true;
        }

        String query = request.getURI().getQuery();

        // 2) agentId query fallback (내부 봇 어댑터 — cookie 없음, 사내 망)
        String agentId = queryParam(query, "agentId");
        if (agentId != null) {
            AgentVo agent = agentMapper.selectByIdAnyOwner(agentId);
            if (agent != null && agent.getOwnerAccountSn() != null) {
                attributes.put(MessageWebSocketHandler.ATTR_ACCOUNT_SN, agent.getOwnerAccountSn());
                attributes.put(MessageWebSocketHandler.ATTR_AGENT_ID, agentId);
                return true;
            }
            log.warn("[ws-handshake] reject — agentId={} not found", agentId);
            return false;
        }

        // 3) Bearer token query — 외부 AI (Phase 2)
        String rawToken = queryParam(query, "token");
        if (BearerTokenUtil.looksLikeBearerToken(rawToken)) {
            AgentVo agent = agentMapper.selectByBearerTokenHash(tokenUtil.hash(rawToken));
            if (agent != null) {
                attributes.put(MessageWebSocketHandler.ATTR_ACCOUNT_SN, agent.getOwnerAccountSn());
                attributes.put(MessageWebSocketHandler.ATTR_AGENT_ID, agent.getAgentId());
                return true;
            }
            log.warn("[ws-handshake] reject — bearer token not matched");
            return false;
        }

        log.warn("[ws-handshake] reject — no cookie principal, no agentId, no token (path={})",
                request.getURI().getPath());
        return false;
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                WebSocketHandler wsHandler, Exception exception) {
        // no-op
    }

    /** 단순 querystring parser — `key=value&...` 형식에서 key 의 첫 값 반환. */
    private static String queryParam(String query, String key) {
        if (query == null || query.isEmpty()) return null;
        for (String pair : query.split("&")) {
            int eq = pair.indexOf('=');
            if (eq <= 0) continue;
            String k = pair.substring(0, eq);
            if (key.equals(k)) {
                return java.net.URLDecoder.decode(pair.substring(eq + 1), java.nio.charset.StandardCharsets.UTF_8);
            }
        }
        return null;
    }
}
