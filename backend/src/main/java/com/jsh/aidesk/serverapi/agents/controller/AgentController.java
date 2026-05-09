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
}
