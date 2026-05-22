package com.jsh.aidesk.serverapi.messages.retry;

import java.time.OffsetDateTime;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.lastmile.LastMileAdapter;
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * Helper 의 ACK 가 일정 시간 안에 안 도착하면 last-mile 을 재발행한다.
 *
 * SSE 의 emitter.send() 는 TCP buffer 까지 전달된 것만 보장하므로 helper 가 실제 받았는지
 * 모른다 (half-open 등). end-to-end ACK 로 'delivered' 마킹하고, ACK 누락 시 본 스케줄러가
 * 재시도. 최대 재시도 횟수 도달 시 'failed' 로 마킹하고 송신자에게 errorReason 노출.
 *
 * 모든 처리는 fail-safe — 한 메시지에서 예외가 나도 다른 메시지 처리는 계속.
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class MessageRetryScheduler {

    /** ACK 대기 시간. 이 시간이 지나도 status='sent' 이면 재발행 대상. application.yaml 외부화. */
    @Value("${messages.retry.ack-timeout-sec:5}")
    private int ackTimeoutSec;
    /** 최대 재시도 횟수. 초회 발행은 retry_count=0, 1회 retry 후 1, …, MAX 도달 시 failed. */
    @Value("${messages.retry.max-retries:60}")
    private int maxRetries;
    /** 한 번에 처리할 최대 메시지 수 — DB 부담 방지. */
    @Value("${messages.retry.batch-limit:50}")
    private int batchLimit;
    /** 수신자 helper offline 판정 임계 (last_seen stale 초). 이 이상이면 재시도 안 하고 즉시 failed. */
    @Value("${messages.retry.recipient-offline-sec:60}")
    private int recipientOfflineSec;

    private final MessageMapper messageMapper;
    private final AgentMapper agentMapper;
    private final LastMileAdapter lastMile;

    /**
     * 5초마다 stale 'sent' 메시지 search → 재발행 또는 failed 마킹.
     * 첫 발행은 MessageService.send 가 했고, 본 스케줄러는 그 후 ACK 누락 케이스 처리만.
     */
    @Scheduled(fixedDelay = 3000, initialDelay = 10_000)
    public void retryStale() {
        List<MessageVo> stale;
        try {
            stale = messageMapper.selectStaleSent(ackTimeoutSec, maxRetries, batchLimit);
        } catch (Exception e) {
            log.warn("retry: selectStaleSent failed: {}", e.getMessage());
            return;
        }
        if (stale.isEmpty()) return;
        log.info("retry: {} stale 'sent' message(s) — re-publishing", stale.size());
        for (MessageVo m : stale) {
            try {
                processOne(m);
            } catch (Exception e) {
                log.warn("retry: msg={} processOne failed: {}", m.getMessageId(), e.getMessage());
            }
        }
    }

    @Transactional
    protected void processOne(MessageVo m) {
        if (m.getRetryCount() != null && m.getRetryCount() >= maxRetries - 1) {
            // 한 번 더 시도하면 MAX 도달 — 그냥 failed.
            messageMapper.markFailed(m.getMessageId(),
                    "Helper ACK 미수신 (재시도 " + maxRetries + "회 모두 실패)");
            log.warn("retry: msg={} marked failed (max retries reached)", m.getMessageId());
            return;
        }
        // 스케줄러는 시스템 콜 — owner 격리 없이 sender/receiver 정체 확인.
        AgentVo from = agentMapper.selectByIdAnyOwner(m.getFromAgentId());
        AgentVo to = agentMapper.selectByIdAnyOwner(m.getToAgentId());
        if (from == null || to == null) {
            messageMapper.markFailed(m.getMessageId(), "발신자/수신자 에이전트 조회 실패");
            return;
        }

        // 수신자 휴먼: tmux 없음 → 채팅 UI 폴링이 가져감. 'delivered' 마킹으로 흐름 복구.
        if ("human".equalsIgnoreCase(to.getModel())) {
            messageMapper.markDelivered(m.getMessageId());
            log.info("retry: msg={} recipient is human — marked delivered (UI polling will pick up)",
                    m.getMessageId());
            return;
        }

        // 옵션 1: 수신자 helper 가 offline 이면 재시도해도 도달 불가 → 즉시 failed.
        // last_seen_at 은 helper reporter 의 마지막 touch (현재는 agent.updated_at 매핑).
        OffsetDateTime lastSeen = to.getUpdatedAt();
        if (lastSeen != null
                && lastSeen.isBefore(OffsetDateTime.now().minusSeconds(recipientOfflineSec))) {
            messageMapper.markFailed(m.getMessageId(),
                    "수신자 helper 오프라인 (last_seen " + recipientOfflineSec + "초 이상 stale)");
            log.warn("retry: msg={} marked failed — recipient {}({}) offline (lastSeen={})",
                    m.getMessageId(), to.getAgentName(), to.getAgentId(), lastSeen);
            return;
        }

        messageMapper.bumpRetry(m.getMessageId());
        lastMile.deliver(m, from, to, new LastMileAdapter.DeliveryCallback() {
            @Override
            public void onDelivered() {
                // 재발행도 ACK 기반 — SseLastMileAdapter 는 호출 안 함.
            }
            @Override
            public void onFailed(String reason) {
                messageMapper.markFailed(m.getMessageId(), reason);
                log.warn("retry: msg={} publish failed: {}", m.getMessageId(), reason);
            }
        });
        log.info("retry: msg={} re-published (attempt {})",
                m.getMessageId(), (m.getRetryCount() == null ? 1 : m.getRetryCount() + 1));
    }
}
