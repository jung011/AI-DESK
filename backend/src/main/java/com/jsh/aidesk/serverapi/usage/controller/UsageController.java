package com.jsh.aidesk.serverapi.usage.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
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

    @PostMapping("/install-statusline")
    public ResponseJson<Void> installStatusline() {
        int rc = usageService.installStatuslineHook();
        return switch (rc) {
            case 0 -> ResponseJson.ok((Void) null);
            case 1 -> ResponseJson.<Void>fail(1, "statusline 스크립트(adesk-cli/bin/aidesk-statusline.js)를 찾지 못했습니다.");
            default -> ResponseJson.<Void>fail(1, "~/.claude/settings.json 갱신에 실패했습니다.");
        };
    }
}
