package com.jsh.aidesk.serverapi.terminal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

import lombok.RequiredArgsConstructor;

/**
 * 대시보드 임베드 터미널용 WebSocket 엔드포인트 등록.
 * `ws://<host>:30081/ws/terminal?session={tmux 세션명}` 으로 연결한다.
 *
 * 허용 origin 은 cors.allowed-origins 와 동일 정책 (CSV) 을 따른다.
 */
@Configuration
@EnableWebSocket
@RequiredArgsConstructor
public class TerminalWebSocketConfig implements WebSocketConfigurer {

    private final TerminalWebSocketHandler handler;

    @Value("${cors.allowed-origins}")
    private String allowedOrigins;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/terminal")
                .setAllowedOrigins(allowedOrigins.split(","));
    }
}
