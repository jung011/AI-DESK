package com.jsh.aidesk.serverapi.messages.lastmile;

import org.springframework.stereotype.Component;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

/**
 * 1단계 last mile stub — 실제 주입 없이 즉시 delivered 콜백을 호출한다.
 *
 * Phase 4 에서 TmuxLastMileAdapter 로 교체될 자리다. 그 시점에 본 클래스는 fallback 으로
 * 유지되거나 삭제된다.
 */
@Component
public class StubLastMileAdapter implements LastMileAdapter {

    @Override
    public void deliver(MessageVo message, AgentVo target, DeliveryCallback callback) {
        callback.onDelivered();
    }
}
