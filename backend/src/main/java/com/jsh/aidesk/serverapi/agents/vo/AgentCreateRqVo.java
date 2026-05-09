package com.jsh.aidesk.serverapi.agents.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class AgentCreateRqVo {

    @NotBlank
    @Size(max = 50)
    private String agentName;

    @NotBlank
    @Size(max = 500)
    @Pattern(regexp = "^/.+", message = "workspaceDir must be an absolute path")
    private String workspaceDir;

    @NotBlank
    @Pattern(regexp = "^(claude|codex|hermes)$",
             message = "model must be one of: claude, codex, hermes")
    private String model;
}
