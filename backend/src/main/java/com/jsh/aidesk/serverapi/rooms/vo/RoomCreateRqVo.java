package com.jsh.aidesk.serverapi.rooms.vo;

import java.util.List;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class RoomCreateRqVo {

    @NotBlank
    @Size(max = 50)
    private String roomName;

    /** 방을 만든 AI. 자동으로 coordinator 멤버로 합류. */
    @NotBlank
    @Size(max = 36)
    private String createdBy;

    /** 생성과 동시에 추가할 일반 멤버 (선택). createdBy 와 중복은 무시. */
    @Size(max = 50)
    private List<@NotBlank @Size(max = 36) String> initialMemberAgentIds;
}
