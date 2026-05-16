package com.jsh.aidesk.serverapi.logs.controller;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.logs.service.LogService;
import com.jsh.aidesk.serverapi.logs.vo.ActionLogCreateRqVo;
import com.jsh.aidesk.serverapi.logs.vo.LogFeedItemRsVo;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@RequestMapping("/api")
@RestController
public class LogController {

    private final LogService logService;

    /** Helper 의 PostToolUse 훅이 호출. */
    @PostMapping("/action-logs")
    public ResponseJson<String> recordAction(@Valid @RequestBody ActionLogCreateRqVo body) {
        return ResponseJson.ok(logService.recordAction(body));
    }

    /** 통합 로그 피드 — 메시지(분류) + 액션을 시간 역순으로 머지. */
    @GetMapping("/logs")
    public ResponseJson<List<LogFeedItemRsVo>> feed(
            @RequestParam(value = "category", required = false) String category,
            @RequestParam(value = "limit", required = false) Integer limit
    ) {
        return ResponseJson.ok(logService.getFeed(category, limit));
    }
}
