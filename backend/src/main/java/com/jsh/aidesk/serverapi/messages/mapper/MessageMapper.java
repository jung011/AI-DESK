package com.jsh.aidesk.serverapi.messages.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

@Mapper
public interface MessageMapper {

    int insert(MessageVo message);

    int updateStatus(@Param("messageId") String messageId,
                     @Param("status") String status,
                     @Param("errorReason") String errorReason);

    MessageVo selectById(@Param("messageId") String messageId);

    /**
     * 단건 조회 — 발신/수신 에이전트 이름 join 포함.
     */
    MessageItemRsVo selectItemById(@Param("messageId") String messageId);

    /**
     * 목록 조회.
     * @param agentId 기준 AI
     * @param direction inbox / outbox / all
     * @param withId 특정 상대 (1:1 대화 추출)
     * @param status 상태 필터
     * @param limit 최대 건수
     */
    List<MessageItemRsVo> selectByAgent(@Param("agentId") String agentId,
                                         @Param("direction") String direction,
                                         @Param("withId") String withId,
                                         @Param("status") String status,
                                         @Param("limit") int limit);

    /**
     * rate limit 검사 — 최근 N초 동안 fromAgentId 가 보낸 건수.
     */
    int countRecentByFrom(@Param("agentId") String agentId,
                          @Param("seconds") int seconds);
}
