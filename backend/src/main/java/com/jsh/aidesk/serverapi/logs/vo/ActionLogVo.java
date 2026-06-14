package com.jsh.aidesk.serverapi.logs.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;

/** t_ai_action_log row 매핑. */
@Getter
@Setter
public class ActionLogVo {
    private String logId;
    private String agentId;
    private String agentName;
    private String sessionId;
    private String tool;
    private String category;
    private String target;
    private String summary;
    private OffsetDateTime createdAt;
}
