package com.jsh.aidesk.serverapi.setting.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.setting.service.SettingService;
import com.jsh.aidesk.serverapi.setting.vo.A2aWorkspaceRqVo;
import com.jsh.aidesk.serverapi.setting.vo.A2aWorkspaceRsVo;
import com.jsh.aidesk.serverapi.setting.vo.CodeServerRsVo;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@RequestMapping("/api/settings")
@RestController
public class SettingController {

    private final SettingService settingService;

    @GetMapping("/a2a-workspace")
    public ResponseJson<A2aWorkspaceRsVo> get() {
        return ResponseJson.ok(new A2aWorkspaceRsVo(settingService.getA2aWorkspace()));
    }

    @GetMapping("/code-server")
    public ResponseJson<CodeServerRsVo> codeServer() {
        return ResponseJson.ok(settingService.getCodeServer());
    }

    @PutMapping("/a2a-workspace")
    public ResponseJson<A2aWorkspaceRsVo> put(@Valid @RequestBody A2aWorkspaceRqVo body) {
        int rc = settingService.setA2aWorkspace(body.getPath());
        return switch (rc) {
            case 0 -> ResponseJson.ok(new A2aWorkspaceRsVo(settingService.getA2aWorkspace()));
            case 1 -> ResponseJson.<A2aWorkspaceRsVo>fail(1, "경로가 비어 있습니다.");
            case 2 -> ResponseJson.<A2aWorkspaceRsVo>fail(1, "존재하지 않거나 디렉토리가 아닙니다.");
            case 3 -> ResponseJson.<A2aWorkspaceRsVo>fail(1, "~/.claude.json 갱신에 실패했습니다.");
            default -> ResponseJson.<A2aWorkspaceRsVo>fail(1, "설정 변경에 실패했습니다.");
        };
    }
}
