package com.jsh.aidesk.serverapi.messages.websocket;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * Frontend ↔ Backend WebSocket 핸들러.
 *
 * 단방향 push 위주 (Phase 0) — 서버가 메시지 INSERT 시 broker.publishToAccount 호출.
 * 클라이언트 → 서버 메시지는 *.PoC 단계 처리 안 함* (POST /api/messages 는 기존 HTTP 그대로).
 *
 * 인증 — {@link JwtHandshakeInterceptor} 가 handshake 단계에서 SecurityContext 의 AuthenticatedUser 추출
 * → session.attributes 에 `accountSn` 저장. 여기서 그것 읽어 broker 에 등록.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class MessageWebSocketHandler extends TextWebSocketHandler {

    public static final String ATTR_ACCOUNT_SN = "accountSn";
    public static final String ATTR_AGENT_ID = "agentId";

    private final MessageWebSocketBroker broker;

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        Long accountSn = (Long) session.getAttributes().get(ATTR_ACCOUNT_SN);
        if (accountSn == null) {
            log.warn("[ws-handler] handshake passed but accountSn missing — closing session={}", session.getId());
            session.close(CloseStatus.POLICY_VIOLATION);
            return;
        }
        broker.register(accountSn, session);
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        Long accountSn = (Long) session.getAttributes().get(ATTR_ACCOUNT_SN);
        if (accountSn != null) {
            broker.unregister(accountSn, session);
        }
        log.info("[ws-handler] closed session={} status={}", session.getId(), status);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        // PoC: 클라이언트 → 서버 메시지는 처리 안 함. 송신은 POST /api/messages HTTP 그대로 유지.
        log.debug("[ws-handler] received (ignored) session={} len={}", session.getId(), message.getPayloadLength());
    }
}
