package com.jsh.aidesk.serverapi.desktop.controller;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.desktop.service.DesktopService;
import com.jsh.aidesk.serverapi.desktop.vo.DesktopLocalInfoRqVo;
import com.jsh.aidesk.serverapi.desktop.vo.DesktopLocalInfoRsVo;

import lombok.RequiredArgsConstructor;

/**
 * Desktop Agent ↔ 중앙 백엔드 통신 엔드포인트.
 *
 * - `POST /api/desktop/local-info`: Agent 가 본인 Mac 의 워크스페이스/tmux 스냅샷을 업로드
 *   하고, 백엔드는 t_ai_agent 의 status 를 갱신한다.
 *
 * 1단계 PoC: 인증 없음. M6 단계에서 JWT 인증 추가 예정.
 */
@RequiredArgsConstructor
@RequestMapping("/api/desktop")
@RestController
public class DesktopController {

    private final DesktopService desktopService;

    @PostMapping("/local-info")
    public ResponseJson<DesktopLocalInfoRsVo> uploadLocalInfo(
            @RequestBody DesktopLocalInfoRqVo body) {
        return ResponseJson.ok(desktopService.applyLocalInfo(body));
    }
}
