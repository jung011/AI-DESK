package com.jsh.aidesk.serverapi.external.controller;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

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
}
