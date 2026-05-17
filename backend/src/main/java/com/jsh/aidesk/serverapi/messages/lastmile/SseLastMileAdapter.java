package com.jsh.aidesk.serverapi.messages.lastmile;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.desktop.sse.DesktopEventBroker;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * Desktop Agent 에게 SSE `message.deliver` 이벤트를 발행해 last-mile 을 위임하는 어댑터.
 *
 * 실제 `tmux send-keys` 는 Helper(Python) 가 수행하므로 백엔드는 macOS 종속 코드를
 * 보유할 필요가 없다 — Docker 컨테이너 안에서도 동일하게 동작.
 *
 * 페이로드:
 *   { "messageId", "fromAgentName", "toTmuxSession", "content" }
 *
 * 동작 정책:
 *   - publish 성공 (subscriber >= 1)  → 콜백 호출 없음. status='sent' 유지하고 Helper 의 ACK 를 기다린다.
 *                                       ACK 가 일정 시간 안에 안 오면 RetryScheduler 가 재발행.
 *   - publish 실패 (subscriber = 0)  → onFailed("Helper 미연결").
 *
 * 이전엔 publish 성공 = onDelivered() 호출이었는데, SSE 의 emitter.send() 성공은
 * 단지 TCP buffer 까지 전달된 것이라 helper 가 실제 받았다는 보장이 아님 (half-open 등).
 * 그래서 false-positive delivered 마킹이 발생 → 메시지 손실. End-to-end ACK 로 전환.
 */
@Component
@Primary
@Slf4j
@RequiredArgsConstructor
public class SseLastMileAdapter implements LastMileAdapter {

    private final DesktopEventBroker broker;

    @Override
    public void deliver(MessageVo message, AgentVo from, AgentVo to, DeliveryCallback callback) {
        String session = to.getTmuxSession();
        if (session == null || session.isBlank()) {
            callback.onFailed("수신 AI 세션 없음 (tmux_session 미설정)");
            return;
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("messageId", message.getMessageId());
        payload.put("fromAgentName", from.getAgentName());
        payload.put("toAgentName", to.getAgentName());
        payload.put("toTmuxSession", session);
        payload.put("content", message.getContent());

        int n = broker.publish("message.deliver", payload);
        if (n == 0) {
            callback.onFailed("Helper 미연결 (SSE 구독자 없음)");
            return;
        }
        log.info("[message-publish] msg={} to={}({}) subscribers={} — awaiting helper ACK",
                message.getMessageId(), to.getAgentName(), to.getTmuxSession(), n);
        // 의도적으로 onDelivered() 호출 안 함. Helper 의 ACK 가 도착해야 status='delivered'.
    }
}
