package com.jsh.aidesk.serverapi.agents.vo;

import java.time.OffsetDateTime;
import java.util.List;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

/**
 * GET /api/agents/realtime 응답 항목 — 메타버스 3D 화면 등 외부 시각화 BE 가 소비.
 *
 * state 5종 (working / idle / talking / awaiting_input / offline) 으로 backend 가 합성:
 *  - lastSeenAt < NOW()-60s → offline (최상위)
 *  - status='error' → offline
 *  - 60s 내 partners 있음 → talking
 *  - status='active' → working
 *  - status='waiting' → awaiting_input
 *  - status='idle' → idle
 */
@Getter
@Setter
@ToString
public class AgentRealtimeRsVo {

    private String agentId;
    private String name;
    /** working | idle | talking | awaiting_input | offline */
    private String state;
    /** 최근 60초 내 대화 활동이 있는 distinct 상대 agentId 배열. */
    private List<String> partners;
    /** helper reporter 마지막 신고 시각 (= t_ai_agent.updated_at). offline 판정 + 외부 BE 의 내부 판단용. */
    private OffsetDateTime lastSeenAt;
}
