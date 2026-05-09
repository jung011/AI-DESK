package com.jsh.aidesk.serverapi.messages.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

/**
 * 대화 목록 단건 — 좌측 패널에 표시되는 한 행.
 */
@Getter
@Setter
@ToString
public class ConversationItemRsVo {

    /** 상대 AI 정보 */
    private String partnerAgentId;
    private String partnerAgentName;
    private String partnerStatus;
    private String partnerWorkspaceDir;

    /** 마지막 메시지 정보 */
    private String lastMessageId;
    private String lastMessageContent;
    private OffsetDateTime lastActivityAt;
    /** 마지막 메시지의 방향: inbox(상대→나) / outbox(나→상대) */
    private String lastDirection;

    /** 미확인 수신 메시지 수 (read_at IS NULL AND from_agent_id = partner) */
    private int unreadCount;
}
