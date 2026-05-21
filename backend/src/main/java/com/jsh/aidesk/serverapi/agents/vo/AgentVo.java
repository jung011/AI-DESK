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
}
