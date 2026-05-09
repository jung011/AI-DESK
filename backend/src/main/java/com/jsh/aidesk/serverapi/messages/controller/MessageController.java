package com.jsh.aidesk.serverapi.messages.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.messages.service.MessageService;
import com.jsh.aidesk.serverapi.messages.vo.MessageCreateRqVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageListRsVo;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@RequestMapping("/api/messages")
@RestController
public class MessageController {

    private final MessageService messageService;

    @PostMapping
    public ResponseJson<MessageItemRsVo> create(@Valid @RequestBody MessageCreateRqVo body) {
        return ResponseJson.ok(messageService.create(body));
    }

    @GetMapping
    public ResponseJson<MessageListRsVo> list(
            @RequestParam("agentId") String agentId,
            @RequestParam(value = "direction", defaultValue = "all") String direction,
            @RequestParam(value = "withId", required = false) String withId,
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "limit", defaultValue = "100") int limit) {
        return ResponseJson.ok(messageService.getList(agentId, direction, withId, status, limit));
    }
}
