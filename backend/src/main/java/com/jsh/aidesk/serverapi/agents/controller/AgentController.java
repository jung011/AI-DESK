package com.jsh.aidesk.serverapi.agents.controller;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.agents.service.AgentService;
import com.jsh.aidesk.serverapi.agents.vo.AgentCreateRqVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentItemRsVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentListRsVo;
import com.jsh.aidesk.serverapi.common.response.ResponseCode;
import com.jsh.aidesk.serverapi.common.response.ResponseJson;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@RequestMapping("/api/agents")
@RestController
public class AgentController {

    private final AgentService agentService;

    @GetMapping
    public ResponseJson<AgentListRsVo> list(
            @RequestParam(value = "status", required = false) String status) {
        return ResponseJson.ok(agentService.getList(status));
    }

    @GetMapping("/{agentId}")
    public ResponseJson<AgentItemRsVo> detail(@PathVariable("agentId") String agentId) {
        AgentItemRsVo item = agentService.detail(agentId);
        return item == null ? ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND) : ResponseJson.ok(item);
    }

    @PostMapping
    public ResponseJson<AgentItemRsVo> create(@Valid @RequestBody AgentCreateRqVo body) {
        AgentItemRsVo created = agentService.create(body);
        if (created == null) {
            return ResponseJson.fail(ResponseCode.FAIL_REGIST);
        }
        return ResponseJson.ok(created);
    }

    @DeleteMapping("/{agentId}")
    public ResponseJson<Void> delete(@PathVariable("agentId") String agentId) {
        boolean ok = agentService.delete(agentId);
        return ok ? ResponseJson.ok((Void) null) : ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND);
    }

    @PostMapping("/_browse-workspace")
    public ResponseJson<String> browseWorkspace() {
        String path = agentService.browseWorkspace();
        if (path == null) {
            return ResponseJson.<String>fail(1, "현재 백엔드 OS 에서는 폴더 선택 다이얼로그를 지원하지 않습니다 (macOS 한정).");
        }
        // 빈 문자열은 사용자 취소 — 정상 응답으로 내려보내고 프론트에서 무시한다.
        return ResponseJson.ok(path);
    }

    @PostMapping("/{agentId}/open-terminal")
    public ResponseJson<Void> openTerminal(@PathVariable("agentId") String agentId) {
        int rc = agentService.openTerminal(agentId);
        return switch (rc) {
            case 0 -> ResponseJson.ok((Void) null);
            case 1 -> ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND);
            case 2 -> ResponseJson.<Void>fail(1, "워크스페이스 경로가 없습니다.");
            case 3 -> ResponseJson.<Void>fail(1, "현재 백엔드 OS 에서는 터미널 열기를 지원하지 않습니다 (macOS 한정).");
            default -> ResponseJson.<Void>fail(1, "터미널 실행에 실패했습니다.");
        };
    }

    @PostMapping("/{agentId}/open-vscode")
    public ResponseJson<Void> openVscode(@PathVariable("agentId") String agentId) {
        int rc = agentService.openVscode(agentId);
        return switch (rc) {
            case 0 -> ResponseJson.ok((Void) null);
            case 1 -> ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND);
            case 2 -> ResponseJson.<Void>fail(1, "워크스페이스 경로가 없습니다.");
            case 3 -> ResponseJson.<Void>fail(1, "현재 백엔드 OS 에서는 VSCode 열기를 지원하지 않습니다.");
            default -> ResponseJson.<Void>fail(1, "code CLI 실행에 실패했습니다. VSCode 에서 ‘Install code in PATH’ 가 되어있는지 확인하세요.");
        };
    }
}
