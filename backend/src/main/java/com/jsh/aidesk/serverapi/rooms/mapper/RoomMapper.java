package com.jsh.aidesk.serverapi.rooms.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.jsh.aidesk.serverapi.rooms.vo.RoomItemRsVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMemberRefRsVo;
import com.jsh.aidesk.serverapi.rooms.vo.RoomMessageItemRsVo;

@Mapper
public interface RoomMapper {

    int insertRoom(@Param("roomId") String roomId,
                   @Param("roomName") String roomName,
                   @Param("createdBy") String createdBy);

    int insertMember(@Param("roomId") String roomId,
                     @Param("agentId") String agentId,
                     @Param("role") String role);

    /** 단건 조회 (멤버는 별도 쿼리). archived 도 포함. */
    RoomItemRsVo selectRoomById(@Param("roomId") String roomId);

    /** 지정 AI 가 멤버인 룸 목록 (archived 제외). 멤버는 별도 쿼리. */
    List<RoomItemRsVo> selectRoomsByAgent(@Param("agentId") String agentId);

    List<RoomMemberRefRsVo> selectMembers(@Param("roomId") String roomId);

    int isMember(@Param("roomId") String roomId, @Param("agentId") String agentId);

    int insertMessage(@Param("messageId") String messageId,
                      @Param("roomId") String roomId,
                      @Param("fromAgentId") String fromAgentId,
                      @Param("content") String content);

    List<RoomMessageItemRsVo> selectMessages(@Param("roomId") String roomId,
                                              @Param("limit") int limit);
}
