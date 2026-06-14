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

    /**
     * true 면 옛 + 새 워크스페이스의 .jsonl 대화 기록을 모두 삭제하고 (me) tmux 세션도 kill.
     * 옛 워크스페이스를 같은 경로에 재생성한 뒤 claude --resume 으로 옛 대화 복원되는 케이스 끊기용.
     * 기본 false — 작업 보존 우선.
     */
    private boolean purgePreviousHistory = false;
}
