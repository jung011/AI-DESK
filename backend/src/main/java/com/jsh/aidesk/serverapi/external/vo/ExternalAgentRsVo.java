package com.jsh.aidesk.serverapi.external.vo;

import java.util.List;

import lombok.Getter;
import lombok.Setter;

/**
 * 사내 kaflix-a2a Control Plane 의 `/v1/agents/lite` 에서 가져온 외부 직원 에이전트.
 * 대시보드의 "사내 동료 AI" 섹션 카드 + 클릭 시 스킬 모달에 필요한 필드.
 */
@Getter
@Setter
public class ExternalAgentRsVo {
    private String employeeId;
    private String name;
    private String department;
    private boolean online;
    private List<String> skills;
    /** 이 백엔드를 운영하는 본인 여부 (kaflix.me-employee-id 와 employeeId 가 일치). */
    private boolean me;
}
