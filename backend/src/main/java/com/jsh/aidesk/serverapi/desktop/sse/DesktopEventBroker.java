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
     * SSE 채널 활성 유지용 heartbeat.
     *
     * SSE 의 *comment line* (`: heartbeat`) 만 발송 — 클라이언트의 event 핸들러는 안 탐.
     * 목적: 중간 layer (ingress proxy, LB idle timeout, VPN DPD 등) 가 *event 없는 idle 연결*
     *      을 silent 하게 끊는 zombie TCP 패턴 방지. helper 0.6.20 의 read timeout (120s) 이
     *      매번 발동되기 전에 우리 쪽에서 30초마다 활성 신호를 보내 둠으로써:
     *        - 중간 layer 의 idle timeout 회피 (대부분 60s~10분)
     *        - 진짜로 끊긴 emitter 는 IOException 으로 즉시 감지 + 자동 정리
     */
    @Scheduled(fixedDelay = 30_000L, initialDelay = 30_000L)
    public void heartbeat() {
        if (emitters.isEmpty()) return;
        int alive = 0;
        for (SseEmitter emitter : emitters) {
            try {
                emitter.send(SseEmitter.event().comment("hb"));
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
