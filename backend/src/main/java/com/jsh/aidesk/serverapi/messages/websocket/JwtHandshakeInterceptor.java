package com.jsh.aidesk.serverapi.messages.websocket;

import java.util.Map;

import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import com.jsh.aidesk.serverapi.common.jwt.AuthenticatedUser;

import lombok.extern.slf4j.Slf4j;

/**
 * WebSocket handshake 시점에 SecurityContext 의 AuthenticatedUser 추출 → session.attributes 에 accountSn 저장.
 * 인증 안 된 handshake 는 거부 (false 반환).
 *
 * 동작 전제: JwtAuthenticationFilter 가 WebSocket upgrade HTTP request 도 거쳐가며
 * SecurityContextHolder 에 AuthenticatedUser principal 을 미리 세팅. (Spring Security 표준 흐름)
 */
@Slf4j
public class JwtHandshakeInterceptor implements HandshakeInterceptor {

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                    WebSocketHandler wsHandler, Map<String, Object> attributes) {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !(auth.getPrincipal() instanceof AuthenticatedUser user)) {
            log.warn("[ws-handshake] reject — no AuthenticatedUser principal (path={})",
                    request.getURI().getPath());
            return false;
        }
        attributes.put(MessageWebSocketHandler.ATTR_ACCOUNT_SN, user.getAccountSn());
        return true;
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                WebSocketHandler wsHandler, Exception exception) {
        // no-op
    }
}
