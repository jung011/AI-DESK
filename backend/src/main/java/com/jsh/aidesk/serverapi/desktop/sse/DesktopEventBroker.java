package com.jsh.aidesk.serverapi.desktop.sse;

import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import lombok.extern.slf4j.Slf4j;

/**
 * Desktop Agent 들과의 SSE(server-sent events) 채널을 관리한다.
 *
 * 사용 흐름:
 *   - Helper 가 `GET /api/desktop/events` 로 구독 → subscribe() 가 새 SseEmitter 반환
 *   - 백엔드의 last-mile (SseLastMileAdapter) 이 publish() 로 이벤트 발행
 *   - 발행은 현재 활성인 모든 구독자에게 broadcast (single-user PoC).
 *     멀티유저 라우팅은 Phase 6 인증 도입 이후 employeeId 기반으로 좁힌다.
 */
@Component
@Slf4j
public class DesktopEventBroker {

    private static final long KEEP_ALIVE_MS = 0L;

    private final Set<SseEmitter> emitters = ConcurrentHashMap.newKeySet();

    public SseEmitter subscribe() {
        // 0L = 타임아웃 없음 (Helper 가 무기한 유지). 끊김은 transport 단에서 잡힌다.
        SseEmitter emitter = new SseEmitter(KEEP_ALIVE_MS);
        emitters.add(emitter);
        emitter.onCompletion(() -> {
            emitters.remove(emitter);
            log.info("[sse-emitter] completed — helper SSE 정상 종료 (subscribers={})", emitters.size());
        });
        emitter.onTimeout(() -> {
            emitters.remove(emitter);
            log.warn("[sse-emitter] TIMEOUT — helper 미응답 / half-open 가능성 (subscribers={})", emitters.size());
        });
        emitter.onError(t -> {
            emitters.remove(emitter);
            log.warn("[sse-emitter] ERROR — helper 연결 끊김: {} (subscribers={})",
                    t.getMessage(), emitters.size());
        });
        // 응답 헤더를 즉시 flush 하기 위한 초기 이벤트.
        // 없으면 첫 진짜 이벤트가 발행될 때까지 클라이언트가 connecting 상태에 갇힘.
        try {
            emitter.send(SseEmitter.event().name("hello").data("ok"));
        } catch (IOException e) {
            emitters.remove(emitter);
            log.debug("SSE hello flush failed: {}", e.getMessage());
        }
        log.info("SSE subscriber added (subscribers={})", emitters.size());
        return emitter;
    }

    /** 활성 구독자에게 이벤트 발행. 끊긴 구독자는 자동 정리. 발행 성공한 구독자 수 반환. */
    public int publish(String eventName, Object data) {
        int delivered = 0;
        for (SseEmitter emitter : emitters) {
            try {
                emitter.send(SseEmitter.event().name(eventName).data(data));
                delivered++;
            } catch (IOException ex) {
                emitters.remove(emitter);
                log.warn("[sse-publish] DROP — emitter 끊김, subscriber 제거 (남은={}): {}",
                        emitters.size(), ex.getMessage());
            }
        }
        return delivered;
    }

    /**
     * SSE 채널 활성 유지용 heartbeat — *named event* 로 발송.
     *
     * 옛엔 *comment line* (`: hb`) 만 보냈는데, helper (httpx-sse) 의 `aiter_sse()` 가
     * comment-only line 을 *event 로 yield 하지 않아* helper 0.7.5+ 의 watchdog 의
     * `mark_sse_event()` 가 호출 안 됨 → 90s 후 false-positive self-kill.
     *
     * 해결: `event: heartbeat\ndata: {}\n\n` 형태의 *named event* 로 발송 → helper 의
     * `aiter_sse()` 가 정상 yield → mark_sse_event() 호출 → idle timer 갱신 → self-kill 차단.
     *
     * 효과는 동일 — 중간 layer (ingress / LB / VPN DPD) idle timeout 회피 + 끊긴 emitter 는
     * IOException 으로 즉시 감지 + 자동 정리.
     */
    @Scheduled(fixedDelay = 30_000L, initialDelay = 30_000L)
    public void heartbeat() {
        if (emitters.isEmpty()) return;
        int alive = 0;
        for (SseEmitter emitter : emitters) {
            try {
                emitter.send(SseEmitter.event().name("heartbeat").data("{}"));
                alive++;
            } catch (IOException ex) {
                emitters.remove(emitter);
                log.warn("[sse-heartbeat] DROP — emitter 끊김 감지, subscriber 제거 (남은={}): {}",
                        emitters.size(), ex.getMessage());
            }
        }
        if (log.isDebugEnabled()) {
            log.debug("[sse-heartbeat] sent to {} emitter(s)", alive);
        }
    }
}
