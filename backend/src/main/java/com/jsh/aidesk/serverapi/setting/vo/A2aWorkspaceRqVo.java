package com.jsh.aidesk.serverapi.setting.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class A2aWorkspaceRqVo {
    @NotBlank
    @Size(max = 500)
    private String path;
}
