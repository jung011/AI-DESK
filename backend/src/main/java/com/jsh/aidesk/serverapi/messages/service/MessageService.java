package com.jsh.aidesk.serverapi.messages.service;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.lastmile.LastMileAdapter;
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;
import com.jsh.aidesk.serverapi.messages.policy.MessagePolicyChecker;
import com.jsh.aidesk.serverapi.messages.policy.PolicyResult;
import java.util.List;

import com.jsh.aidesk.serverapi.messages.vo.AgentUnreadRsVo;
import com.jsh.aidesk.serverapi.messages.vo.ConversationItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageCreateRqVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageListRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;
import com.jsh.aidesk.serverapi.messages.vo.UnreadCountRsVo;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class MessageService {

    private final MessageMapper messageMapper;
    private final AgentMapper agentMapper;
    private final MessagePolicyChecker policy;
    private final LastMileAdapter lastMile;

    /**
     * 메시지 발신.
     *
     * 1) 양 끝 에이전트 존재 확인 (없으면 404)
     * 2) self-message → 400
     * 3) 부모 메시지 (있으면) 조회
     * 4) 정책 검사 — 위반은 status=failed 로 INSERT 후 그대로 응답
     * 5) 정책 통과 → status=sent INSERT 후 last mile 호출
     * 6) 갱신된 단건을 envelope.data 로 반환
     */
    @Transactional
    public MessageItemRsVo create(MessageCreateRqVo req) {
        AgentVo from = agentMapper.selectById(req.getFromAgentId());
        AgentVo to = agentMapper.selectById(req.getToAgentId());
        if (from == null || to == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "발신/수신 AI 미존재");
        }
        if (from.getAgentId().equals(to.getAgentId())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "self-message");
        }

        MessageVo parent = null;
        if (req.getReplyToMessageId() != null && !req.getReplyToMessageId().isBlank()) {
            parent = messageMapper.selectById(req.getReplyToMessageId());
            if (parent == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "원본 메시지 미존재");
            }
        }

        MessageVo entity = new MessageVo();
        entity.setMessageId(UUID.randomUUID().toString());
        entity.setFromAgentId(from.getAgentId());
        entity.setToAgentId(to.getAgentId());
        entity.setContent(req.getContent());
        entity.setReplyToMessageId(req.getReplyToMessageId());
        if (parent != null) {
            int newHop = (parent.getHopCount() == null ? 0 : parent.getHopCount()) + 1;
            entity.setHopCount(newHop);
            entity.setRootMessageId(parent.getRootMessageId() != null
                    ? parent.getRootMessageId() : parent.getMessageId());
        } else {
            entity.setHopCount(0);
        }

        // 4. 정책 검사
        PolicyResult result = policy.check(from, to, parent);
        if (!result.accepted()) {
            entity.setStatus("failed");
            entity.setErrorReason(result.errorReason());
            messageMapper.insert(entity);
            return messageMapper.selectItemById(entity.getMessageId());
        }

        // 5. INSERT + last mile
        entity.setStatus("sent");
        messageMapper.insert(entity);

        final String messageId = entity.getMessageId();
        final String parentId = parent != null ? parent.getMessageId() : null;
        lastMile.deliver(entity, to, new LastMileAdapter.DeliveryCallback() {
            @Override
            public void onDelivered() {
                messageMapper.updateStatus(messageId, "delivered", null);
                if (parentId != null) {
                    messageMapper.updateParentReplied(parentId);
                }
            }
            @Override
            public void onFailed(String reason) {
                messageMapper.updateStatus(messageId, "failed", reason);
            }
        });

        return messageMapper.selectItemById(messageId);
    }

    /**
     * 메시지 읽음 처리. 본인 수신 메시지가 아니면 변경 없음.
     */
    @Transactional
    public boolean markRead(String messageId, String agentId) {
        return messageMapper.updateRead(messageId, agentId) > 0;
    }

    /**
     * 대화 목록 (좌측 패널) — 지정 AI 가 참여한 대화별로 마지막 메시지 + unreadCount.
     */
    @Transactional(readOnly = true)
    public List<ConversationItemRsVo> getConversations(String agentId) {
        return messageMapper.selectConversations(agentId);
    }

    /**
     * 미확인 수신 메시지 수 — 전체 합 + 에이전트별 분해.
     * agentId 가 주어지면 그 에이전트의 수만 반환.
     */
    @Transactional(readOnly = true)
    public UnreadCountRsVo getUnreadCount(String agentId) {
        List<AgentUnreadRsVo> all = messageMapper.selectUnreadCounts();
        UnreadCountRsVo rs = new UnreadCountRsVo();
        if (agentId != null && !agentId.isBlank()) {
            List<AgentUnreadRsVo> filtered = all.stream()
                    .filter(a -> agentId.equals(a.getAgentId()))
                    .toList();
            rs.setByAgent(filtered);
            rs.setTotalUnread(filtered.stream().mapToInt(AgentUnreadRsVo::getUnread).sum());
        } else {
            rs.setByAgent(all);
            rs.setTotalUnread(all.stream().mapToInt(AgentUnreadRsVo::getUnread).sum());
        }
        return rs;
    }

    /**
     * 메시지 목록 조회.
     */
    @Transactional(readOnly = true)
    public MessageListRsVo getList(String agentId, String direction, String withId,
                                   String status, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 500));
        var list = messageMapper.selectByAgent(agentId, direction, withId, status, safeLimit + 1);
        boolean hasMore = list.size() > safeLimit;
        if (hasMore) list = list.subList(0, safeLimit);
        MessageListRsVo rs = new MessageListRsVo();
        rs.setList(list);
        rs.setHasMore(hasMore);
        return rs;
    }
}
