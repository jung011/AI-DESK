package com.jsh.aidesk.serverapi.external.controller;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseCode;
import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.external.service.ExternalAgentService;
import com.jsh.aidesk.serverapi.external.vo.ExternalAgentRsVo;

import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@RequestMapping("/api/external-agents")
@RestController
public class ExternalAgentController {

    private final ExternalAgentService externalAgentService;

    @GetMapping
    public ResponseJson<List<ExternalAgentRsVo>> list() {
        return ResponseJson.ok(externalAgentService.list());
    }

    @PostMapping("/{employeeId}/open-terminal")
    public ResponseJson<Void> openTerminal(@PathVariable("employeeId") String employeeId) {
        int rc = externalAgentService.openTerminal(employeeId);
        return switch (rc) {
            case 0 -> ResponseJson.ok((Void) null);
            case 1 -> ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND);
            case 2 -> ResponseJson.<Void>fail(1, "동료 터미널 워크스페이스가 설정되어 있지 않습니다 (kaflix.colleague-terminal-workspace).");
            case 3 -> ResponseJson.<Void>fail(1, "현재 백엔드 OS 에서는 터미널 열기를 지원하지 않습니다 (macOS 한정).");
            default -> ResponseJson.<Void>fail(1, "터미널 실행에 실패했습니다.");
        };
    }
}
