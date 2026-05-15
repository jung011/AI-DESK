package com.jsh.aidesk.serverapi.desktop.vo;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class DesktopLocalInfoRsVo {
    /** Helper 가 보고한 워크스페이스 개수 (필터링 전). */
    private int totalWorkspaces;
    /** workspace_dir 로 t_ai_agent 와 매칭된 개수. */
    private int matchedAgents;
    /** status 가 실제로 바뀌어 DB 업데이트가 일어난 개수. */
    private int updatedAgents;
}
