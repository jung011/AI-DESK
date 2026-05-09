package com.jsh.aidesk.serverapi.rooms.vo;

import java.time.OffsetDateTime;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class RoomMemberRefRsVo {

    private String agentId;
    private String agentName;
    private String role;
    private OffsetDateTime joinedAt;
}
