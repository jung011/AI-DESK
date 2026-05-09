package com.jsh.aidesk.serverapi.rooms.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class RoomMessageItemRsVo {

    private String messageId;
    private String roomId;
    private String fromAgentId;
    private String fromAgentName;
    private String content;
    private OffsetDateTime createdAt;
}
