package com.jsh.aidesk.serverapi.agents.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class AgentItemRsVo {

    private String agentId;
    private String agentName;
    private String workspaceDir;
    private String tmuxSession;
    private String status;
    private String taskDesc;
    private String model;
    private Integer contextPct;
    private OffsetDateTime startedAt;
    private OffsetDateTime updatedAt;

    /** 발신자의 시점에서 본 agent 분류. channel/channel_backend.md §4 참조. */
    private Long ownerAccountSn;
    /** "self" | "me" | "internal" | "human" | "colleague". null = caller 정보 미상. */
    private String type;
}
