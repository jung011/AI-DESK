package com.jsh.aidesk.serverapi.agents.controller;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

import com.jsh.aidesk.serverapi.agents.service.AgentService;
import com.jsh.aidesk.serverapi.agents.vo.AgentCreateRqVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentItemRsVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentListRsVo;
import com.jsh.aidesk.serverapi.agents.vo.AgentRealtimeRsVo;
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
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "callerAgentId", required = false) String callerAgentId) {
        return ResponseJson.ok(agentService.getList(status, callerAgentId));
    }

    /**
     * 외부 시각화 BE (메타버스 3D 화면 등) 가 소비하는 realtime 통합 응답.
     * 응답 5필드 = agentId, name, state(working/idle/talking/awaiting_input/offline), partners[], lastSeenAt.
     */
    @GetMapping("/realtime")
    public ResponseJson<List<AgentRealtimeRsVo>> realtime() {
        return ResponseJson.ok(agentService.getRealtime());
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

}
