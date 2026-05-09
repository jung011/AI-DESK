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

    /**
     * 단건 읽음 처리 — 본인 (to_agent_id == agentId) 메시지에만 적용.
     * 0건 반환 = 매치 없음 또는 이미 읽음.
     */
    int updateRead(@Param("messageId") String messageId,
                   @Param("agentId") String agentId);

    /**
     * 부모 메시지의 status 를 replied 로 갱신 (replied_at = NOW()).
     * POST /api/messages with replyToMessageId 의 last mile delivered 콜백에서 호출.
     */
    int updateParentReplied(@Param("messageId") String messageId);

    /**
     * 대화 목록 — 지정 AI 가 참여한 대화별로 마지막 메시지 + unread count.
     */
    List<com.jsh.aidesk.serverapi.messages.vo.ConversationItemRsVo>
        selectConversations(@Param("agentId") String agentId);

    /**
     * AI 별 미확인 수신 메시지 수.
     * status IN (delivered, replied) AND read_at IS NULL 만 카운트.
     */
    List<com.jsh.aidesk.serverapi.messages.vo.AgentUnreadRsVo> selectUnreadCounts();

    /**
     * 감사 로그 — 모든 메시지를 시간 역순으로. 필터는 모두 선택.
     * q 는 본문 부분 일치 (ILIKE).
     */
    List<com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo> selectAudit(
            @Param("status") String status,
            @Param("fromAgentId") String fromAgentId,
            @Param("toAgentId") String toAgentId,
            @Param("q") String q,
            @Param("limit") int limit);
}
