/**
 * 백엔드 REST 호출용 $fetch 인스턴스.
 *
 * 주요 책임:
 * - baseURL 주입 (runtimeConfig.public.apiBase).
 * - 인증 cookie (HttpOnly accessToken / refreshToken) 자동 첨부 (`credentials: 'include'`).
 * - 401 ET 응답 받으면 /api/auth/refresh 자동 호출 → 성공 시 원 요청 재시도,
 *   실패 시 store.clearUser + /login redirect (sample axios 인터셉터 패턴 동일).
 * - 401 NA 응답 받으면 즉시 store.clearUser + /login redirect.
 *
 * 사용:
 *   const { $api } = useNuxtApp();
 *   const res = await $api<MyType>('/api/agents');
 */
import { useAuthStore } from '~/stores/auth';
import { clientLog } from '~/utils/clientLogger';

// refresh 동시 다발성 큐잉 — 한 번에 한 refresh 만 진행.
let refreshPromise: Promise<boolean> | null = null;

export default defineNuxtPlugin(() => {
  const config = useRuntimeConfig();
  const baseURL = config.public.apiBase as string;

  const isAuthEndpoint = (path: string) =>
    path.startsWith('/api/auth/authenticate') ||
    path.startsWith('/api/auth/refresh') ||
    path.startsWith('/api/auth/signup');

  const tryRefresh = async (): Promise<boolean> => {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
      const started = Date.now();
      try {
        const res = await $fetch<{ result: number }>('/api/auth/refresh', {
          baseURL,
          method: 'POST',
          credentials: 'include',
        });
        const ok = res?.result === 0;
        // 2026-06-30 ws 1006 진단 — refresh 결과 명시 trace. nav-debug 의 'fetch:result'
        // 가 본 path 의 4xx 만 잡으니 *성공 / 결과* 도 별도 로깅. 사고 시점에 refresh
        // 가 호출됐는지 / 성공했는지 / 어느 응답이었는지 backend stdout + DB 둘 다 보존.
        clientLog('log', 'auth-refresh:done', { ok, result: res?.result, elapsedMs: Date.now() - started });
        return ok;
      } catch (e) {
        clientLog('warn', 'auth-refresh:throw', { message: String((e as Error)?.message ?? e), elapsedMs: Date.now() - started });
        return false;
      } finally {
        // 다음 refresh 가능하도록 마이크로태스크 뒤에 비움
        setTimeout(() => { refreshPromise = null; }, 0);
      }
    })();
    return refreshPromise;
  };

  const redirectToLogin = (reason?: string) => {
    if (!import.meta.client) return;
    const auth = useAuthStore();
    const route = useRoute();
    // 옛 [[feedback-jwt-expired-vs-invalid]] 의 진단 path — 백엔드 K8s log 박혀있는
    // app.client 채널 안 영구 보존. console 새로고침 사고 회피.
    // visibility / referrer / cookie length 같은 *추가 단서* 같이 박음.
    const cookieRaw = (typeof document !== 'undefined' ? document.cookie : '') || '';
    clientLog('error', 'redirectToLogin', {
      reason: reason ?? 'unknown',
      currentRoute: route.fullPath,
      hasSession: !!window.sessionStorage.getItem('aidesk.auth'),
      visibilityState: typeof document !== 'undefined' ? document.visibilityState : '?',
      referrer: typeof document !== 'undefined' ? (document.referrer || '').slice(0, 120) : '?',
      cookieLength: cookieRaw.length,
      // cookie value 자체 X (HttpOnly 라 어차피 없음) — length 만 진단 용
      ua: typeof navigator !== 'undefined' ? (navigator.userAgent || '').slice(0, 120) : '?',
    });
    auth.clearUser();
    const router = useRouter();
    if (route.path !== '/login') {
      router.replace({ path: '/login', query: { redirect: route.fullPath } });
    }
  };

  const api = $fetch.create({
    baseURL,
    credentials: 'include',

    async onResponseError(ctx) {
      const status = ctx.response?.status;
      if (status !== 401) return;

      // /api/auth/* 자신의 401 은 인터셉터 개입 X — 호출자가 알아서 처리.
      const path = String(ctx.request);
      if (isAuthEndpoint(path)) return;

      const body = ctx.response?._data as { code?: string } | undefined;
      const code = body?.code;

      // 2026-06-30 ws 1006 진단 — 모든 401 받은 시점을 path + code 함께 trace. ET refresh
      // 가 호출되었는지 / NA redirect 가 호출되었는지 / 둘 다 아닌 case 가 있는지 backend
      // stdout + DB 영구 보존. 옛 *조용히 사라짐* 사고 root cause 잡기 위해 필수.
      clientLog('log', 'api:401', { path, code: code ?? '(missing)', hasBody: !!body });

      // ET: access 만료 → refresh 후 원 요청 재시도. 한 번만 시도해 무한 루프 방지.
      const opts = ctx.options as unknown as { _retried?: boolean };
      if (code === 'ET' && !opts._retried) {
        const ok = await tryRefresh();
        if (ok) {
          opts._retried = true;
          try {
            const retried = await $fetch(ctx.request as string, {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              ...(ctx.options as any),
              baseURL,
              credentials: 'include',
            });
            if (ctx.response) {
              ctx.response._data = retried;
              Object.defineProperty(ctx.response, 'status', { value: 200, configurable: true });
            }
            return;
          } catch (e) {
            clientLog('error', 'ET retry failed', { path, error: String(e) });
          }
        }
        redirectToLogin(`ET refresh fail (path=${path})`);
        return;
      }

      // NA: access 자체 없음/위조 → 즉시 로그인 화면
      if (code === 'NA') {
        redirectToLogin(`NA (path=${path})`);
      }
    },
  });

  return {
    provide: { api },
  };
});
