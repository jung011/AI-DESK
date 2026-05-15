package com.jsh.aidesk.serverapi.desktop.controller;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.desktop.service.DesktopService;
import com.jsh.aidesk.serverapi.desktop.sse.DesktopEventBroker;
import com.jsh.aidesk.serverapi.desktop.vo.DesktopLocalInfoRqVo;
import com.jsh.aidesk.serverapi.desktop.vo.DesktopLocalInfoRsVo;

import lombok.RequiredArgsConstructor;

/**
 * Desktop Agent ↔ 중앙 백엔드 통신 엔드포인트.
 *
 * - `POST /api/desktop/local-info`: Agent 가 본인 Mac 의 워크스페이스/tmux 스냅샷 업로드
 * - `GET  /api/desktop/events`    : Agent 가 메시지 last-mile 등 푸시를 받기 위한 SSE 채널
 *
 * 1단계 PoC: 인증 없음. M6 단계에서 JWT 인증 추가 예정.
 */
@RequiredArgsConstructor
@RequestMapping("/api/desktop")
@RestController
public class DesktopController {

    private final DesktopService desktopService;
    private final DesktopEventBroker desktopEventBroker;

    @PostMapping("/local-info")
    public ResponseJson<DesktopLocalInfoRsVo> uploadLocalInfo(
            @RequestBody DesktopLocalInfoRqVo body) {
        return ResponseJson.ok(desktopService.applyLocalInfo(body));
    }

    @GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events() {
        return desktopEventBroker.subscribe();
    }
}
