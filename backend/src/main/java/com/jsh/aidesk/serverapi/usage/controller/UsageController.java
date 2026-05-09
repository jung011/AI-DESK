package com.jsh.aidesk.serverapi.usage.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.usage.service.UsageService;
import com.jsh.aidesk.serverapi.usage.vo.LocalUsageRsVo;

import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@RequestMapping("/api/usage")
@RestController
public class UsageController {

    private final UsageService usageService;

    @GetMapping("/local")
    public ResponseJson<LocalUsageRsVo> local() {
        return ResponseJson.ok(usageService.getLocalUsage());
    }
}
