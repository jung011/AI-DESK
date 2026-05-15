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
 * Helper 가 한 명이라도 구독 중이면 onDelivered, 아니면 onFailed.
 * 실제 tmux 도달 여부는 별도 ACK(Phase 6 이후) 로 받기로 하고 PoC 단계에선 낙관 처리.
 */
@Component
@Primary
@Slf4j
@RequiredArgsConstructor
public class SseLastMileAdapter implements LastMileAdapter {

    /**
     * 발신 트랜잭션(INSERT) 이 commit 되기 전에 onDelivered 의 UPDATE 가 먼저 돌면
     * 0 rows update 가 되어 status 가 sent 에 그대로 머문다. SSE 발행은 in-memory 라
     * 즉시 끝나므로 commit race 가 쉽게 노출된다.
     *
     * 짧은 가드 슬립으로 회피. 100~150ms 면 일반 INSERT 트랜잭션 commit 시간을 충분히 덮음.
     * 더 견고한 해결은 MessageService 단에서 TransactionSynchronization.afterCommit 으로
     * 디스패치를 옮기는 것 (Phase 6 이후 정리 후보).
     */
    private static final long COMMIT_RACE_GUARD_MS = 150L;

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
        log.debug("message.deliver published → {} subscribers (msg={} to={})",
                n, message.getMessageId(), to.getAgentName());
        try {
            Thread.sleep(COMMIT_RACE_GUARD_MS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        callback.onDelivered();
    }
}
