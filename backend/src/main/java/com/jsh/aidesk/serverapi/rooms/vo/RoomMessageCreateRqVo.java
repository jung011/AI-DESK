package com.jsh.aidesk.serverapi.rooms.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class RoomMessageCreateRqVo {

    @NotBlank
    @Size(max = 36)
    private String fromAgentId;

    @NotBlank
    @Size(max = 1000)
    private String content;
}
