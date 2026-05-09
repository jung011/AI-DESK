package com.jsh.aidesk.serverapi.messages.lastmile;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

/**
 * 즉시 delivered 콜백을 호출하는 stub 어댑터.
 *
 * 운영 시에는 TmuxLastMileAdapter (@Primary) 가 우선 주입된다.
 * 이 클래스는 단위 테스트용으로 새 인스턴스를 직접 생성해 사용하거나,
 * 향후 환경별 분기에서 fallback 으로 활용된다.
 *
 * Component 빈으로 등록하지 않는다 — 활성 어댑터 충돌을 피한다.
 */
public class StubLastMileAdapter implements LastMileAdapter {

    @Override
    public void deliver(MessageVo message, AgentVo from, AgentVo to, DeliveryCallback callback) {
        callback.onDelivered();
    }
}
