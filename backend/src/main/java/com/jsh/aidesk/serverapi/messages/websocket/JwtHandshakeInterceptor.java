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
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.common.jwt.AuthenticatedUser;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * WebSocket handshake 인증 — 두 경로 허용:
 *   1. cookie JWT 가 SecurityContext 에 AuthenticatedUser 를 세팅한 경우 (브라우저 chat UI)
 *   2. ?agentId=<UUID> query 가 있으면 t_ai_agent 에서 owner 를 찾아 fallback (내부 봇 어댑터)
 *
 * (2) 는 backend 의 /api/messages /api/agents 가 이미 permitAll + sender agent 의 owner 로
 * fallback 하는 패턴과 동일 — 같은 user 의 다른 agent 끼리 인증 우회. UUID 는 cross-account
 * isolation 으로 다른 user 의 agentId 가 노출되지 않으므로 사내 망 안에선 충분.
 *
 * 외부 AI 합류 (Phase 2) 시점에 (2) 자리를 Bearer token 인증으로 강화 예정.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class JwtHandshakeInterceptor implements HandshakeInterceptor {

    private final AgentMapper agentMapper;

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                    WebSocketHandler wsHandler, Map<String, Object> attributes) {
        // 1) cookie JWT 인증
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof AuthenticatedUser user) {
            attributes.put(MessageWebSocketHandler.ATTR_ACCOUNT_SN, user.getAccountSn());
            return true;
        }

        // 2) agentId query fallback (내부 봇 어댑터 — cookie 없음)
        String agentId = queryParam(request.getURI().getQuery(), "agentId");
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

        log.warn("[ws-handshake] reject — no cookie principal and no agentId query (path={})",
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
