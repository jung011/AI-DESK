package com.jsh.aidesk.serverapi.rooms.service;

import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.rooms.mapper.RoomMapper;
import com.jsh.aidesk.serverapi.rooms.vo.RoomCreateRqVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomItemRsVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMemberRefRsVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMessageCreateRqVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMessageItemRsVo;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class RoomService {

    private final RoomMapper roomMapper;
    private final AgentMapper agentMapper;

    /**
     * 룸 생성. createdBy 는 자동으로 coordinator 로 합류.
     * initialMemberAgentIds 의 각 AI 도 일반 멤버로 추가 (createdBy 와 중복은 스킵).
     */
    @Transactional
    public RoomItemRsVo create(RoomCreateRqVo req) {
        if (agentMapper.selectById(req.getCreatedBy()) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "createdBy AI 미존재");
        }

        String roomId = UUID.randomUUID().toString();
        roomMapper.insertRoom(roomId, req.getRoomName(), req.getCreatedBy());
        roomMapper.insertMember(roomId, req.getCreatedBy(), "coordinator");

        if (req.getInitialMemberAgentIds() != null) {
            for (String memberId : req.getInitialMemberAgentIds()) {
                if (memberId == null || memberId.isBlank()) continue;
                if (memberId.equals(req.getCreatedBy())) continue;
                if (agentMapper.selectById(memberId) == null) continue;
                roomMapper.insertMember(roomId, memberId, "member");
            }
        }
        return getRoom(roomId);
    }

    @Transactional(readOnly = true)
    public RoomItemRsVo getRoom(String roomId) {
        RoomItemRsVo room = roomMapper.selectRoomById(roomId);
        if (room == null) return null;
        room.setMembers(roomMapper.selectMembers(roomId));
        return room;
    }

    @Transactional(readOnly = true)
    public List<RoomItemRsVo> getRoomsByAgent(String agentId) {
        List<RoomItemRsVo> list = roomMapper.selectRoomsByAgent(agentId);
        for (RoomItemRsVo r : list) {
            r.setMembers(roomMapper.selectMembers(r.getRoomId()));
        }
        return list;
    }

    @Transactional
    public RoomMemberRefRsVo addMember(String roomId, String agentId, String role) {
        if (roomMapper.selectRoomById(roomId) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "방 미존재");
        }
        if (agentMapper.selectById(agentId) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "AI 미존재");
        }
        roomMapper.insertMember(roomId, agentId, role == null ? "member" : role);
        return roomMapper.selectMembers(roomId).stream()
                .filter(m -> agentId.equals(m.getAgentId()))
                .findFirst()
                .orElse(null);
    }

    @Transactional
    public RoomMessageItemRsVo sendMessage(String roomId, RoomMessageCreateRqVo req) {
        if (roomMapper.selectRoomById(roomId) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "방 미존재");
        }
        if (roomMapper.isMember(roomId, req.getFromAgentId()) == 0) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "방 멤버가 아닙니다");
        }
        String messageId = UUID.randomUUID().toString();
        roomMapper.insertMessage(messageId, roomId, req.getFromAgentId(), req.getContent());
        return roomMapper.selectMessages(roomId, Integer.MAX_VALUE).stream()
                .filter(m -> messageId.equals(m.getMessageId()))
                .findFirst()
                .orElse(null);
    }

    @Transactional(readOnly = true)
    public List<RoomMessageItemRsVo> getMessages(String roomId, int limit) {
        if (roomMapper.selectRoomById(roomId) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "방 미존재");
        }
        return roomMapper.selectMessages(roomId, Math.max(1, Math.min(limit, 1000)));
    }
}
