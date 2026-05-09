package com.jsh.aidesk.serverapi.messages.lastmile;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

/**
 * 메시지 last mile 어댑터.
 *
 * - 1단계 : Stub 구현 (즉시 delivered) — 실제 tmux 주입은 Phase 4 의 TmuxLastMileAdapter
 * - 2단계 : aidesk-channel MCP 서버에 push (McpLastMileAdapter)
 *
 * 호출은 비동기 가정. 결과는 콜백으로 전달한다.
 */
public interface LastMileAdapter {

    void deliver(MessageVo message, AgentVo target, DeliveryCallback callback);

    interface DeliveryCallback {
        void onDelivered();

        void onFailed(String reason);
    }
}
