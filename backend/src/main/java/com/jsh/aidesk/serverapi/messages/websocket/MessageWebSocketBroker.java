package com.jsh.aidesk.serverapi.messages.websocket;

import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import lombok.extern.slf4j.Slf4j;

/**
 * Frontend ↔ Backend 의 메시지 push 채널 (Phase 0 — Per-AI 봇 어댑터 plan 의 첫 단추).
 *
 * Helper 측 SSE ({@link com.jsh.aidesk.serverapi.desktop.sse.DesktopEventBroker}) 와는 *별개*.
 *  - Helper SSE  : tmux 안 AI 의 last-mile (backend → helper → tmux send-keys)
 *  - Frontend WS : 브라우저 / PWA 채팅창의 실시간 push (backend → 사용자 브라우저)
 *
 * 사용자(accountSn) 별로 active session 들을 그룹화 — 한 사용자가 multi tab / multi device 로
 * 동시 접속 가능. recipient_account_sn 매칭으로 *정확히 본인에게만* push (broadcast PoC 한계 회피).
 */
@Component
@Slf4j
public class MessageWebSocketBroker {

    /** accountSn → 활성 WebSocket sessions. 한 사용자의 모든 tab / device 가 같은 set 에 등록. */
    private final ConcurrentMap<Long, Set<WebSocketSession>> sessionsByAccount = new ConcurrentHashMap<>();

    public void register(Long accountSn, WebSocketSession session) {
        sessionsByAccount.computeIfAbsent(accountSn, k -> ConcurrentHashMap.newKeySet()).add(session);
        log.info("[ws-broker] register accountSn={} session={} totalSessions={}",
                accountSn, session.getId(), totalSessionCount());
    }

    public void unregister(Long accountSn, WebSocketSession session) {
        Set<WebSocketSession> set = sessionsByAccount.get(accountSn);
        if (set == null) return;
        set.remove(session);
        if (set.isEmpty()) {
            sessionsByAccount.remove(accountSn);
        }
        log.info("[ws-broker] unregister accountSn={} session={} totalSessions={}",
                accountSn, session.getId(), totalSessionCount());
    }

    /**
     * 특정 사용자 accountSn 의 모든 활성 session 에 payload push.
     * dead session 은 send 실패로 감지되며 다음 close 콜백으로 정리.
     */
    public void publishToAccount(Long accountSn, String payload) {
        Set<WebSocketSession> set = sessionsByAccount.get(accountSn);
        if (set == null || set.isEmpty()) {
            return;
        }
        TextMessage msg = new TextMessage(payload);
        for (WebSocketSession s : set) {
            try {
                if (s.isOpen()) {
                    s.sendMessage(msg);
                }
            } catch (IOException e) {
                log.warn("[ws-broker] send failed accountSn={} session={}: {}",
                        accountSn, s.getId(), e.getMessage());
            }
        }
    }

    private int totalSessionCount() {
        return sessionsByAccount.values().stream().mapToInt(Set::size).sum();
    }
}
