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
    private String agentName;
    private String workspaceDir;
    private String tmuxSession;
    private String status;
    private String taskDesc;
    private String model;
    private Integer contextPct;
    private OffsetDateTime startedAt;
    private OffsetDateTime updatedAt;
    private OffsetDateTime deletedAt;
}
