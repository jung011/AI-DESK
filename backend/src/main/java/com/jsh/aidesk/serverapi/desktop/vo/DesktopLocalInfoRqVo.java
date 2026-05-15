package com.jsh.aidesk.serverapi.desktop.vo;

import java.util.List;

import lombok.Getter;
import lombok.Setter;

/**
 * Desktop Agent 가 `POST /api/desktop/local-info` 로 보내는 본인 Mac 의 스냅샷.
 */
@Getter
@Setter
public class DesktopLocalInfoRqVo {
    private List<WorkspaceItemRqVo> workspaces;
    private List<TmuxSessionItemRqVo> tmuxSessions;
}
