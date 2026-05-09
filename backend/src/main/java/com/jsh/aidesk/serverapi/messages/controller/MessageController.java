package com.jsh.aidesk.serverapi.messages.controller;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseCode;
import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.messages.service.MessageService;
import com.jsh.aidesk.serverapi.messages.vo.ConversationItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageBroadcastRqVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageBroadcastRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageCreateRqVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageListRsVo;
import com.jsh.aidesk.serverapi.messages.vo.UnreadCountRsVo;

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

    @PostMapping("/broadcast")
    public ResponseJson<MessageBroadcastRsVo> broadcast(
            @Valid @RequestBody MessageBroadcastRqVo body) {
        return ResponseJson.ok(messageService.broadcast(body));
    }

    @GetMapping("/{messageId}")
    public ResponseJson<MessageItemRsVo> detail(@PathVariable("messageId") String messageId) {
        MessageItemRsVo m = messageService.detail(messageId);
        return m == null ? ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND) : ResponseJson.ok(m);
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

    @GetMapping("/conversations")
    public ResponseJson<List<ConversationItemRsVo>> conversations(
            @RequestParam("agentId") String agentId) {
        return ResponseJson.ok(messageService.getConversations(agentId));
    }

    @GetMapping("/unread-count")
    public ResponseJson<UnreadCountRsVo> unreadCount(
            @RequestParam(value = "agentId", required = false) String agentId) {
        return ResponseJson.ok(messageService.getUnreadCount(agentId));
    }

    @PatchMapping("/{messageId}/read")
    public ResponseJson<Void> markRead(
            @PathVariable("messageId") String messageId,
            @RequestParam("agentId") String agentId) {
        boolean ok = messageService.markRead(messageId, agentId);
        return ok ? ResponseJson.ok((Void) null) : ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND);
    }
}
