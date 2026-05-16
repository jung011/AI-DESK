package com.jsh.aidesk.serverapi.logs.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/** Helper 가 PostToolUse 훅에서 호출. agentId 는 식별 안 될 수도 있어 nullable. */
@Getter
@Setter
public class ActionLogCreateRqVo {
    @Size(max = 36)
    private String agentId;

    @Size(max = 50)
    private String agentName;

    @Size(max = 80)
    private String sessionId;

    /** Helper 의 cwd — 백엔드가 등록된 AI Desk 워커 에이전트와 매핑하는 키. 매핑 안 되면 액션 무시. */
    @Size(max = 500)
    private String cwd;

    @NotBlank
    @Size(max = 50)
    private String tool;

    /** code | schema | file | command */
    @NotBlank
    @Size(max = 20)
    private String category;

    @Size(max = 500)
    private String target;

    @Size(max = 500)
    private String summary;
}
