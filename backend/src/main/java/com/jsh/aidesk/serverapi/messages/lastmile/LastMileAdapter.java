package com.jsh.aidesk.serverapi.messages.lastmile;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

/**
 * 메시지 last mile 어댑터 — 백엔드 DB 에 INSERT 된 메시지를 수신자 Claude 까지 실제로 옮긴다.
 *
 * 현재 구현: {@link SseLastMileAdapter} (@Primary) — SSE 푸시로 Helper 알리고, Helper 가
 * `tmux send-keys` 로 수신자 tmux pane 에 주입한다.
 *
 * 실제 호출은 Service 단에서 Virtual Thread 로 비동기 처리한다 (메서드 자체는 동기).
 */
public interface LastMileAdapter {

    void deliver(MessageVo message, AgentVo from, AgentVo to, DeliveryCallback callback);

    interface DeliveryCallback {
        void onDelivered();

        void onFailed(String reason);
    }
}
