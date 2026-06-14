package com.jsh.aidesk.serverapi.agents.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class AgentVo {

    private String agentId;
    /** 에이전트 소유 사용자 (t_user.account_sn). multi-user 격리에서 모든 조회/생성이 이 키로 필터링. */
    private Long ownerAccountSn;
    private String agentName;
    private String workspaceDir;
    private String tmuxSession;
    private String status;
    private String taskDesc;
    private String model;
    private Integer contextPct;
    private boolean bootstrapApplied;
    private OffsetDateTime startedAt;
    private OffsetDateTime updatedAt;
    private OffsetDateTime deletedAt;
    /** 에이전트 분류 — internal / external / me / human. Phase 2 의 인증 분기 + UI 아이콘 기반. */
    private String agentType;
    /** 외부 AI 의 Bearer token BCrypt 해시. 인증 분기에서만 사용. response 직렬화는 절대 X. */
    private String bearerTokenHash;
    /** 외부 AI 의 현재 활성 Bearer token 발급 시각 (감사 + UI 표시). */
    private OffsetDateTime bearerTokenCreatedAt;
}
