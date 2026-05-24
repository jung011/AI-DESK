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
 *   - publish 실패 (subscriber = 0)  → onFailed("수신자 helper SSE 미연결").
 *
 * 이전엔 publish 성공 = onDelivered() 호출이었는데, SSE 의 emitter.send() 성공은
 * 단지 TCP buffer 까지 전달된 것이라 helper 가 실제 받았다는 보장이 아님 (half-open 등).
 * 그래서 false-positive delivered 마킹이 발생 → 메시지 손실. End-to-end ACK 로 전환.
 *
 * 옵션 2 (subscribers=0 즉시 onFailed) 도입 배경:
 * 옛엔 n=0 일 때 status='sent' 그대로 두고 RetryScheduler 가 helper reconnect 후 재발행하기를
 * 기대했음. 그러나 *reporter (HTTP POST) 는 살아있고 SSE 만 dead* 한 분리 상태가 발견됨
 * (우드 측 1.23-rc1 swap 후 케이스). 이때 옵션 1 (lastSeen stale) 은 reporter 기준이라
 * 발동 안 함 → status='sent' + deliveredAt=null 무한 대기 (maxRetries × retry-interval 시간).
 * → n=0 즉시 failed 로 송신자에게 명확히 통지. helper 가 막 reconnect 중인 짧은 윈도우의
 *   false-positive 위험은 있지만, 무한 대기보다 즉시 실패 신호 + 재전송 시도가 더 명확.
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
            // 옵션 2: subscribers=0 = SSE active emitter 없음. helper reporter 가 살아있어도
            // (옵션 1 의 lastSeen 은 recent) SSE 만 dead 인 분리 상태에선 retry 도 영원히
            // n=0 만 반환 → status='sent' 무한 대기. 즉시 onFailed 로 송신자에게 통지.
            log.warn("[message-publish] msg={} to={}({}) subscribers=0 — failing fast (옵션 2)",
                    message.getMessageId(), to.getAgentName(), to.getTmuxSession());
            callback.onFailed("수신자 helper SSE 미연결 (active emitter 없음)");
            return;
        }
        log.info("[message-publish] msg={} to={}({}) subscribers={} — awaiting helper ACK",
                message.getMessageId(), to.getAgentName(), to.getTmuxSession(), n);
        // 의도적으로 onDelivered() 호출 안 함. Helper 의 ACK 가 도착해야 status='delivered'.
    }
}
