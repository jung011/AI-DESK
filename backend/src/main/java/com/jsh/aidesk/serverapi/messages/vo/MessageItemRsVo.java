package com.jsh.aidesk.serverapi.messages.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

/**
 * 메시지 단건 응답 — 발신/수신 에이전트 이름까지 평탄하게 포함.
 */
@Getter
@Setter
@ToString
public class MessageItemRsVo {

    private String messageId;
    private String fromAgentId;
    private String fromAgentName;
    private String toAgentId;
    private String toAgentName;
    private String content;
    private String replyToMessageId;
    private String status;
    private String errorReason;
    private OffsetDateTime createdAt;
    private OffsetDateTime deliveredAt;
    private OffsetDateTime readAt;
    private OffsetDateTime repliedAt;
}
