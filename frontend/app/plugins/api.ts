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
      try {
        const res = await $fetch<{ result: number }>('/api/auth/refresh', {
          baseURL,
          method: 'POST',
          credentials: 'include',
        });
        return res?.result === 0;
      } catch {
        return false;
      } finally {
        // 다음 refresh 가능하도록 마이크로태스크 뒤에 비움
        setTimeout(() => { refreshPromise = null; }, 0);
      }
    })();
    return refreshPromise;
  };

  const redirectToLogin = () => {
    if (!import.meta.client) return;
    const auth = useAuthStore();
    auth.clearUser();
    const router = useRouter();
    const route = useRoute();
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
          } catch {
            // 재시도도 실패 — 아래 redirect 로 떨어짐
          }
        }
        redirectToLogin();
        return;
      }

      // NA: access 자체 없음/위조 → 즉시 로그인 화면
      if (code === 'NA') {
        redirectToLogin();
      }
    },
  });

  return {
    provide: { api },
  };
});
