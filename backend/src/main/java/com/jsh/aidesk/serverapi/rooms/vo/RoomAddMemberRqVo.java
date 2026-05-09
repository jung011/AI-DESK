package com.jsh.aidesk.serverapi.rooms.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class RoomAddMemberRqVo {

    @NotBlank
    @Size(max = 36)
    private String agentId;

    @Pattern(regexp = "^(coordinator|member)$",
             message = "role must be coordinator or member")
    private String role;
}
