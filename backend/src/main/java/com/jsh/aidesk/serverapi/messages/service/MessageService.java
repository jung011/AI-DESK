package com.jsh.aidesk.serverapi.messages.service;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.lastmile.LastMileAdapter;
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;
import com.jsh.aidesk.serverapi.messages.policy.MessagePolicyChecker;
import com.jsh.aidesk.serverapi.messages.policy.PolicyResult;
import com.jsh.aidesk.serverapi.messages.websocket.MessageWebSocketBroker;

import java.util.LinkedHashMap;
import java.util.Map;

import lombok.extern.slf4j.Slf4j;
import java.util.List;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.Set;

import com.jsh.aidesk.serverapi.messages.vo.AgentUnreadRsVo;
import com.jsh.aidesk.serverapi.messages.vo.ConversationItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageBroadcastRqVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageBroadcastRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageCreateRqVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageItemRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageListRsVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;
import com.jsh.aidesk.serverapi.messages.vo.UnreadCountRsVo;

import lombok.RequiredArgsConstructor;

@Service
@Slf4j
@RequiredArgsConstructor
public class MessageService {

    private final MessageMapper messageMapper;
    private final AgentMapper agentMapper;
    private final MessagePolicyChecker policy;
    private final LastMileAdapter lastMile;
    private final MessageWebSocketBroker wsBroker;
    private final ObjectMapper objectMapper;

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
        AgentVo from = agentMapper.selectByIdAnyOwner(req.getFromAgentId());
        AgentVo to = agentMapper.selectByIdAnyOwner(req.getToAgentId());
        if (from == null || to == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "발신/수신 AI 미존재");
        }
        // 권한 검증 — channel/channel_backend.md §2 의 (me) 게이트웨이 정책.
        //
        // actor 결정:
        //   - 인증된 호출 (브라우저 cookie) → SecurityContext.accountSn 으로 검증
        //   - 비인증 호출 (외부 터미널의 aidesk-channel mcp) → sender 의 owner 로 user 추정.
        //     mcp 는 본인의 self_agent 만 sender 로 사용하므로 자기 user 외 발신은 일어나지 않음.
        var authedUser = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentUserOrNull();
        Long actor = (authedUser != null) ? authedUser.getAccountSn() : from.getOwnerAccountSn();
        if (!actor.equals(from.getOwnerAccountSn())) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "본인의 에이전트로만 메시지 발신 가능");
        }
        boolean crossUser = !from.getOwnerAccountSn().equals(to.getOwnerAccountSn());
        if (crossUser) {
            // 사내 동료 통신 — (me)/휴먼 ↔ (me)/휴먼 만 허용. 워커끼리 cross-user 직접 통신 차단.
            if (!isMeOrHuman(from) || !isMeOrHuman(to)) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                        "사내 동료 통신은 (me) 또는 휴먼만 가능합니다 — 워커 AI 는 본인 user 안에서만 통신");
            }
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

        // 휴먼(인간 사용자) entity 는 tmux 가 없음 — last-mile 우회.
        // 채팅 UI 가 폴링으로 가져가서 사용자에게 표시하면 됨. 즉시 status='delivered' 마킹.
        boolean toIsHuman = "human".equalsIgnoreCase(to.getModel());

        // 멀티 mac 환경에서 backend → host.docker.internal:30083 preflight 는 *backend 가 도는
        // mac 의 helper* 만 호출하므로 수신자 helper 가 다른 mac 에 있으면 항상 fail.
        // 옛 single-mac 가정의 preflight 제거 — SSE 발송 + helper ack 흐름에 위임:
        //   수신측 helper 가 본인 mac 에 해당 tmux 있으면 send-keys + ack → status='delivered'
        //   없으면 ignore → status 'sent' 그대로 (UI 가 sent 로 표시).

        // 4. 정책 검사
        PolicyResult result = policy.check(from, to, parent);
        if (!result.accepted()) {
            entity.setStatus("failed");
            entity.setErrorReason(result.errorReason());
            messageMapper.insert(entity);
            return messageMapper.selectItemById(entity.getMessageId());
        }

        // 5. INSERT + last mile (virtual thread 로 비동기)
        // pre-flight 통과 → 이전에 'error' 로 박혀있던 수신자라면 'active' 로 자동 복귀.
        if (!toIsHuman && "error".equals(to.getStatus())) {
            agentMapper.updateStatusFromWatcher(to.getAgentId(), "active", null);
            log.info("[message-preflight] cleared 'error' status for to={}({}) — send unblocked",
                    to.getAgentName(), to.getAgentId());
        }
        entity.setStatus("sent");
        messageMapper.insert(entity);
        log.info("[message-insert] msg={} from={}({}) to={}({}) tmux={}",
                entity.getMessageId(), from.getAgentName(), from.getAgentId(),
                to.getAgentName(), to.getAgentId(), to.getTmuxSession());
        // 부모 'replied' 마킹은 publish 결과와 무관 — INSERT 가 곧 "부모에 답이 옴" 의 확정.
        if (parent != null) {
            messageMapper.updateParentReplied(parent.getMessageId());
        }

        final String messageId = entity.getMessageId();

        // Frontend WS push — recipient 와 sender 의 owner 양쪽 push (multi-tab 동기화).
        // Helper SSE last-mile 과 별개. WS 가 끊긴 사용자는 next polling / reconnect 으로 동기화.
        publishToFrontend(entity, from, to);

        if (toIsHuman) {
            // 휴먼 수신자: tmux send-keys 의미 없음 → 즉시 delivered 마킹. 채팅 UI 폴링이 가져감.
            messageMapper.markDelivered(messageId);
            log.info("[message-deliver-skip] to={}({}) is human — marked delivered immediately",
                    to.getAgentName(), to.getAgentId());
        } else {
            final AgentVo fromAgent = from;
            final AgentVo toAgent = to;
            Thread.startVirtualThread(() -> {
                lastMile.deliver(entity, fromAgent, toAgent, new LastMileAdapter.DeliveryCallback() {
                    @Override
                    public void onDelivered() {
                        // SseLastMileAdapter 는 publish 성공만으로 onDelivered 호출 안 함.
                        // 실제 'delivered' 마킹은 Helper 의 ACK 가 도착해서 markDelivered() 가 불릴 때.
                    }
                    @Override
                    public void onFailed(String reason) {
                        messageMapper.updateStatus(messageId, "failed", reason);
                    }
                });
            });
        }

        return messageMapper.selectItemById(messageId);
    }

    /**
     * 새 메시지를 frontend WS 채널로 push — recipient + sender 의 owner 양쪽 보냄.
     * 같은 user 면 broker 가 ConcurrentMap 의 같은 key 라 자동 한 번만 송신.
     * 실패는 broker 가 흡수 (dead session 은 다음 close 콜백으로 정리).
     */
    private void publishToFrontend(MessageVo message, AgentVo from, AgentVo to) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("type", "message.deliver");
        payload.put("messageId", message.getMessageId());
        payload.put("fromAgentId", from.getAgentId());
        payload.put("fromAgentName", from.getAgentName());
        payload.put("toAgentId", to.getAgentId());
        payload.put("toAgentName", to.getAgentName());
        payload.put("fromAccountSn", from.getOwnerAccountSn());
        payload.put("toAccountSn", to.getOwnerAccountSn());
        payload.put("content", message.getContent());
        payload.put("status", message.getStatus());
        payload.put("createdAt", message.getCreatedAt());

        String json;
        try {
            json = objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException e) {
            log.warn("[ws-publish] payload serialize failed msg={}: {}", message.getMessageId(), e.getMessage());
            return;
        }

        if (to.getOwnerAccountSn() != null) {
            wsBroker.publishToAccount(to.getOwnerAccountSn(), json);
        }
        if (from.getOwnerAccountSn() != null && !from.getOwnerAccountSn().equals(to.getOwnerAccountSn())) {
            wsBroker.publishToAccount(from.getOwnerAccountSn(), json);
        }
    }

    /**
     * 메시지 읽음 처리. 본인 수신 메시지가 아니면 변경 없음.
     */
    @Transactional
    public boolean markRead(String messageId, String agentId) {
        return messageMapper.updateRead(messageId, agentId) > 0;
    }

    /**
     * Helper 의 ACK 처리 — send-keys 가 실제 tmux 에 도달했음을 의미.
     * status='sent' 인 경우만 'delivered' + delivered_at = NOW() 로 마킹.
     * 이미 'delivered'/'replied'/'failed' 면 idempotent.
     */
    @Transactional
    public boolean ackDelivered(String messageId) {
        int n = messageMapper.markDelivered(messageId);
        if (n > 0) {
            log.info("[message-ack] delivered msg={}", messageId);
        }
        return n > 0;
    }

    /**
     * 대화 목록 (좌측 패널) — 지정 AI 가 참여한 대화별로 마지막 메시지 + unreadCount.
     */
    @Transactional(readOnly = true)
    public List<ConversationItemRsVo> getConversations(String agentId) {
        return messageMapper.selectConversations(agentId);
    }

    /**
     * 감사 로그 — 모든 메시지를 시간 역순으로 검색·필터.
     */
    @Transactional(readOnly = true)
    public MessageListRsVo audit(String status, String fromAgentId, String toAgentId, String q, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 1000));
        Long me = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentAccountSn();
        var list = messageMapper.selectAudit(me, status, fromAgentId, toAgentId, q, safeLimit + 1);
        boolean hasMore = list.size() > safeLimit;
        if (hasMore) list = list.subList(0, safeLimit);
        MessageListRsVo rs = new MessageListRsVo();
        rs.setList(list);
        rs.setHasMore(hasMore);
        return rs;
    }

    /**
     * 미확인 수신 메시지 수 — 전체 합 + 에이전트별 분해.
     * agentId 가 주어지면 그 에이전트의 수만 반환.
     */
    @Transactional(readOnly = true)
    public UnreadCountRsVo getUnreadCount(String agentId) {
        Long me = com.jsh.aidesk.serverapi.common.jwt.AuthContext.currentAccountSn();
        List<AgentUnreadRsVo> all = messageMapper.selectUnreadCounts(me);
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
     * 단건 조회.
     */
    @Transactional(readOnly = true)
    public MessageItemRsVo detail(String messageId) {
        return messageMapper.selectItemById(messageId);
    }

    /**
     * 멀티캐스트 발신 — 한 번의 요청을 여러 수신자에게 fan-out.
     *
     * - 자기 자신·중복은 사전 제거
     * - 미존재 수신자는 notFound 카운트로 집계 (예외 X)
     * - 각 수신자별로 create() 의 정책 검사 + INSERT + last mile 동작 그대로 적용
     */
    @Transactional
    public MessageBroadcastRsVo broadcast(MessageBroadcastRqVo req) {
        AgentVo from = agentMapper.selectByIdAnyOwner(req.getFromAgentId());
        if (from == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "발신 AI 미존재");
        }

        Set<String> uniqueTo = new LinkedHashSet<>();
        int duplicateOrSelf = 0;
        for (String id : req.getToAgentIds()) {
            if (id == null || id.isBlank()) continue;
            if (id.equals(from.getAgentId())) { duplicateOrSelf++; continue; }
            if (!uniqueTo.add(id)) duplicateOrSelf++;
        }

        List<MessageItemRsVo> created = new ArrayList<>();
        int notFound = duplicateOrSelf;

        for (String toId : uniqueTo) {
            AgentVo to = agentMapper.selectByIdAnyOwner(toId);
            if (to == null) { notFound++; continue; }

            MessageCreateRqVo single = new MessageCreateRqVo();
            single.setFromAgentId(from.getAgentId());
            single.setToAgentId(toId);
            single.setContent(req.getContent());
            try {
                created.add(create(single));
            } catch (ResponseStatusException ex) {
                // 사전 검증으로 self-message 등은 걸러졌으므로 여기 도달은 드물다.
                notFound++;
            }
        }

        int succ = (int) created.stream()
                .filter(m -> !"failed".equals(m.getStatus()))
                .count();
        int fail = created.size() - succ;

        MessageBroadcastRsVo rs = new MessageBroadcastRsVo();
        rs.setList(created);
        rs.setTotalAttempted(created.size());
        rs.setSucceeded(succ);
        rs.setFailed(fail);
        rs.setNotFound(notFound);
        return rs;
    }

    private static String truncate(String s, int n) {
        if (s == null) return "";
        return s.length() > n ? s.substring(0, n) + "…" : s;
    }

    /**
     * (me) AI 또는 휴먼 entity 판정 — cross-user 메시지 게이트웨이 검증에 사용.
     * - tmux_session 이 "aidesk-self-" prefix 로 시작 = (me)
     * - model 이 "human" = 휴먼
     */
    private static boolean isMeOrHuman(AgentVo a) {
        if (a == null) return false;
        String ts = a.getTmuxSession();
        if (ts != null && ts.startsWith("aidesk-self-")) return true;
        return "human".equalsIgnoreCase(a.getModel());
    }

    /**
     * 메시지 목록 조회.
     *
     * SQL 은 *최근 N개* 를 DESC 로 가져오고 (오래된 메시지 잘림 방지), 응답은
     * 채팅창이 위→아래 시간순으로 그릴 수 있게 ASC 로 reverse 해서 돌려준다.
     */
    @Transactional(readOnly = true)
    public MessageListRsVo getList(String agentId, String direction, String withId,
                                   String status, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 500));
        var rows = messageMapper.selectByAgent(agentId, direction, withId, status, safeLimit + 1);
        boolean hasMore = rows.size() > safeLimit;
        var trimmed = new ArrayList<>(hasMore ? rows.subList(0, safeLimit) : rows);
        java.util.Collections.reverse(trimmed);
        MessageListRsVo rs = new MessageListRsVo();
        rs.setList(trimmed);
        rs.setHasMore(hasMore);
        return rs;
    }
}
