package com.jsh.aidesk.serverapi.messages.lastmile;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

/**
 * 메시지 last mile 어댑터.
 *
 * - 1단계 stub      : NoopLastMileAdapter (즉시 delivered)
 * - 1단계 (Phase 4) : TmuxLastMileAdapter — 실제 tmux 세션에 send-keys
 * - 2단계           : McpLastMileAdapter — aidesk-channel MCP 서버에 push
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
