package com.jsh.aidesk.serverapi.agents.controller;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.agents.service.ExternalAgentService;
import com.jsh.aidesk.serverapi.agents.vo.ExternalAgentCreateRqVo;
import com.jsh.aidesk.serverapi.agents.vo.ExternalAgentTokenRsVo;
import com.jsh.aidesk.serverapi.common.response.ResponseJson;

import lombok.RequiredArgsConstructor;

/**
 * 외부 AI agent 등록 + Bearer token lifecycle.
 *
 * <p>같은 user 의 외부 AI 만 관리 — AuthContext.currentAccountSn 기준 격리.
 *
 * <p>모든 응답의 token 필드는 *생성/회전 시점 1회만* 노출. 사용자는 즉시 외부 service 의
 * 환경 변수에 박아야 함. DB 에는 SHA-256 hash 만 저장돼 이후 복원 불가.
 */
@RequiredArgsConstructor
@RequestMapping("/api/agents/external")
@RestController
public class ExternalAgentController {

    private final ExternalAgentService externalAgentService;

    /** 외부 AI 신규 등록 + 초기 token 발급. body: { agentName }. */
    @PostMapping
    public ResponseJson<ExternalAgentTokenRsVo> create(@RequestBody ExternalAgentCreateRqVo req) {
        return ResponseJson.ok(externalAgentService.create(req));
    }

    /** Token rotate — 새 token 1회 반환. 기존 token 즉시 무효. */
    @PostMapping("/{agentId}/token")
    public ResponseJson<ExternalAgentTokenRsVo> rotateToken(@PathVariable("agentId") String agentId) {
        return ResponseJson.ok(externalAgentService.rotateToken(agentId));
    }

    /** Token revoke — hash 무효화. agent row 자체는 유지 (재발급 가능). */
    @DeleteMapping("/{agentId}/token")
    public ResponseJson<Void> revokeToken(@PathVariable("agentId") String agentId) {
        externalAgentService.revokeToken(agentId);
        // `ResponseJson.ok(null)` 은 ok(CodeData) 로 dispatch 돼 NPE — 명시 cast 로 ok(T) 강제.
        return ResponseJson.ok((Void) null);
    }
}
