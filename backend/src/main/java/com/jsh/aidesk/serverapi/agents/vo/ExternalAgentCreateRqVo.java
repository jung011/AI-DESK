package com.jsh.aidesk.serverapi.agents.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

/**
 * 외부 AI 신규 등록 요청 — 본인 user 의 agent_type='external' row 생성.
 * 외부 AI 의 책임 범위는 통신 채널뿐이므로 본 요청도 이름만 받는다.
 */
@Getter
@Setter
@ToString
public class ExternalAgentCreateRqVo {

    /** 외부 AI 표시 이름 — 사내동료 목록 / 채팅창에 그대로 노출. */
    private String agentName;
}
