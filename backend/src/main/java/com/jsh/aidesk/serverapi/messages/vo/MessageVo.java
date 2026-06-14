package com.jsh.aidesk.serverapi.messages.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class MessageVo {

    private String messageId;
    private String fromAgentId;
    private String toAgentId;
    private String content;
    private String replyToMessageId;
    private String rootMessageId;
    private Integer hopCount;
    private String status;
    private String errorReason;
    private Integer retryCount;
    private OffsetDateTime lastAttemptAt;
    private OffsetDateTime createdAt;
    private OffsetDateTime deliveredAt;
    private OffsetDateTime readAt;
    private OffsetDateTime repliedAt;
}
