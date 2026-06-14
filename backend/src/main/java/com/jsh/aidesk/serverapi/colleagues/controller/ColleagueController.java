package com.jsh.aidesk.serverapi.colleagues.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.colleagues.service.ColleagueService;
import com.jsh.aidesk.serverapi.colleagues.vo.ColleagueListRsVo;
import com.jsh.aidesk.serverapi.common.response.ResponseJson;

import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/colleagues")
@RequiredArgsConstructor
public class ColleagueController {

    private final ColleagueService service;

    /** 사내 동료 list — 같은 backend 의 다른 user 의 (me) AI. */
    @GetMapping
    public ResponseJson<ColleagueListRsVo> list() {
        return ResponseJson.ok(service.getList());
    }
}
