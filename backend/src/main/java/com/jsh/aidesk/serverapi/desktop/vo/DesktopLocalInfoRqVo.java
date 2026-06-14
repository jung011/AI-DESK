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
    /**
     * Helper 가 자신의 kaflix-a2a 사이드카에서 추출한 employeeId.
     * null 이면 사이드카 미가동 또는 카드에 employeeId 누락 — 백엔드는 config 값으로 fallback.
     */
    private String ownerEmployeeId;
    private List<WorkspaceItemRqVo> workspaces;
    private List<TmuxSessionItemRqVo> tmuxSessions;
}
