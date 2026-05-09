package com.jsh.aidesk.serverapi.rooms.vo;

import java.time.OffsetDateTime;
import java.util.List;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class RoomItemRsVo {

    private String roomId;
    private String roomName;
    private String createdBy;
    private String createdByName;
    private OffsetDateTime createdAt;
    private OffsetDateTime archivedAt;

    /** 룸 멤버 목록. 단건 / 목록 응답 모두에 포함. */
    private List<RoomMemberRefRsVo> members;
}
