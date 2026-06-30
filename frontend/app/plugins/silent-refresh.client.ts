/**
 * 주기 silent refresh — JWT access token 만료 (TTL 3600s = 1h) 사전 차단.
 *
 * 옛 사고 패턴 (2026-06-30) — 사용자가 1시간+ 같은 page 머무르다 cookie expire →
 * /api/helper/version 같은 main path 가 401 → ws 도 동시 fail → 사용자 체감 *페이지
 * 사라짐 / 404 / chat 끊김*. rc130 의 진단 인프라가 잡아낸 root cause.
 *
 * 전략: 50분 (3000s) 주기 silent refresh — 1h 만료 직전 buffer. visibility:visible
 * 일 때만 호출 (background tab 의 불필요 traffic 차단). refresh 결과는 api.ts 의
 * tryRefresh path 와 같은 clientLog trace 로 K8s stdout / DB 영구 보존.
 *
 * api.ts 의 401 ET handler 는 *reactive* path (이미 만료된 후 fix). 본 plugin 은
 * *proactive* path — 만료 전 갱신.
 */
import { defineNuxtPlugin } from '#app';
import { useAuthStore } from '~/stores/auth';
import { clientLog } from '~/utils/clientLogger';

const REFRESH_INTERVAL_MS = 50 * 60 * 1000; // 50분 — 1h TTL 의 사전 갱신.

export default defineNuxtPlugin(() => {
  if (typeof window === 'undefined') return;

  let timer: ReturnType<typeof setInterval> | null = null;
  let lastRefreshAt = 0;

  async function silentRefresh(reason: string): Promise<void> {
    const auth = useAuthStore();
    if (!auth.isAuthenticated) return; // 비로그인 사용자엔 호출 X.
    const started = Date.now();
    try {
      const config = useRuntimeConfig();
      const baseURL = config.public.apiBase as string;
      const res = await $fetch<{ result: number }>('/api/auth/refresh', {
        baseURL,
        method: 'POST',
        credentials: 'include',
      });
      const ok = res?.result === 0;
      lastRefreshAt = Date.now();
      clientLog('log', 'silent-refresh:done', { ok, reason, elapsedMs: Date.now() - started });
    } catch (e) {
      // 401 등으로 refresh 자체 fail — api.ts 의 ET / NA handler 가 다음 호출에서 처리.
      clientLog('warn', 'silent-refresh:throw', {
        reason,
        message: String((e as Error)?.message ?? e),
        elapsedMs: Date.now() - started,
      });
    }
  }

  function startTimer(): void {
    if (timer) return;
    timer = setInterval(() => {
      if (document.visibilityState === 'visible') {
        void silentRefresh('interval');
      }
    }, REFRESH_INTERVAL_MS);
  }

  function stopTimer(): void {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  // 페이지 visible 전환 시 — 마지막 refresh 가 50분 이상 전이면 즉시 1회 호출.
  // (background tab 동안 timer fire 가 skip 됐을 가능성 대비.)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      if (Date.now() - lastRefreshAt > REFRESH_INTERVAL_MS) {
        void silentRefresh('visibility');
      }
      startTimer();
    } else {
      // hidden 시 timer 자체는 두기 — visible 전환 시 catchup 으로 보장.
    }
  });

  // 부팅 시 timer 시작. 첫 refresh 는 50분 후 — 로그인 직후 access 는 freshly issued.
  startTimer();
});
