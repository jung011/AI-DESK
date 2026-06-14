package com.jsh.aidesk.serverapi.agents.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Hook 등 외부에서 본인 agent status 만 갱신할 때 사용.
 * 예: claude code 의 PreCompact hook 이 'compacting', PostCompact 가 'idle' 로 복귀.
 */
@Getter
@Setter
public class AgentStatusUpdateRqVo {
    @NotBlank
    @Size(max = 20)
    private String status;
}
