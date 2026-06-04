package com.jsh.aidesk.serverapi.messages.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

import lombok.RequiredArgsConstructor;

/**
 * WebSocket endpoint 등록 — frontend (PWA / dashboard chat) 가 실시간 메시지 push 수신용.
 *
 * Endpoint: `/ws/messages`
 * 인증: JwtHandshakeInterceptor 가 SecurityContext 에서 AuthenticatedUser principal 검증.
 *       cookie (accessToken) 가 유효한 사용자만 handshake 통과.
 */
@Configuration
@EnableWebSocket
@RequiredArgsConstructor
public class WebSocketConfig implements WebSocketConfigurer {

    private final MessageWebSocketHandler handler;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/messages")
                .addInterceptors(new JwtHandshakeInterceptor())
                // CORS — frontend 와 same-origin (nginx proxy) 이라 사실 다 같은 origin 이지만
                // 로컬 dev / 다른 도메인 호환을 위해 패턴 허용. CorsConfig 의 allowed-origins 와 일관.
                .setAllowedOriginPatterns("*");
    }
}
