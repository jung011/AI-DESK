package com.jsh.aidesk.serverapi.rooms.controller;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseCode;
import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.rooms.service.RoomService;
import com.jsh.aidesk.serverapi.rooms.vo.RoomAddMemberRqVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomCreateRqVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomItemRsVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMemberRefRsVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMessageCreateRqVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMessageItemRsVo;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@RequestMapping("/api/rooms")
@RestController
public class RoomController {

    private final RoomService roomService;

    @PostMapping
    public ResponseJson<RoomItemRsVo> create(@Valid @RequestBody RoomCreateRqVo body) {
        return ResponseJson.ok(roomService.create(body));
    }

    @GetMapping
    public ResponseJson<List<RoomItemRsVo>> list(@RequestParam("agentId") String agentId) {
        return ResponseJson.ok(roomService.getRoomsByAgent(agentId));
    }

    @GetMapping("/{roomId}")
    public ResponseJson<RoomItemRsVo> detail(@PathVariable("roomId") String roomId) {
        RoomItemRsVo room = roomService.getRoom(roomId);
        return room == null ? ResponseJson.fail(ResponseCode.FAIL_NOT_FOUND) : ResponseJson.ok(room);
    }

    @PostMapping("/{roomId}/members")
    public ResponseJson<RoomMemberRefRsVo> addMember(
            @PathVariable("roomId") String roomId,
            @Valid @RequestBody RoomAddMemberRqVo body) {
        return ResponseJson.ok(roomService.addMember(roomId, body.getAgentId(), body.getRole()));
    }

    @PostMapping("/{roomId}/messages")
    public ResponseJson<RoomMessageItemRsVo> sendMessage(
            @PathVariable("roomId") String roomId,
            @Valid @RequestBody RoomMessageCreateRqVo body) {
        return ResponseJson.ok(roomService.sendMessage(roomId, body));
    }

    @GetMapping("/{roomId}/messages")
    public ResponseJson<List<RoomMessageItemRsVo>> messages(
            @PathVariable("roomId") String roomId,
            @RequestParam(value = "limit", defaultValue = "200") int limit) {
        return ResponseJson.ok(roomService.getMessages(roomId, limit));
    }
}
