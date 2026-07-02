import { defineNuxtRouteMiddleware, navigateTo } from '#app';
import { useAuthStore } from '~/stores/auth';
import { useHelperVersionStore } from '~/stores/helperVersion';
import { clientLog } from '~/utils/clientLogger';

/**
 * 글로벌 인증 가드 (sample 패턴 동일).
 * - 비로그인 사용자가 PUBLIC 외 경로 접근 → /login (원 경로는 ?redirect= 로 보존)
 * - 로그인된 사용자가 /login 접근 → ?redirect= 또는 /dashboard
 * - 페이지 메타 requiredRoles 가 명시된 경우 사용자 role 미스 → /dashboard 이동
 *   (메타 없으면 검사 스킵 — 모든 인증 사용자 통과)
 *
 * SSR 단계에선 sessionStorage 가 없으므로 client 에서만 동작.
 */
const PUBLIC_PATHS = new Set<string>(['/login']);

/**
 * 로그인 후 redirect 처리 — 절대 URL (http/https) 이면 whitelist (`isExternalRedirectAllowed`) 통과만
 * 외부 browser navigation, 아니면 router path 로 처리.
 * 메타버스 등 cross-domain 진입 흐름에서 navigateTo 가 절대 URL 을 path 로 잘못 해석하는 버그 회피.
 * Whitelist 는 runtime config (ConfigMap env) — 코드에 도메인 hardcode X.
 */
function resolveRedirect(raw: string | undefined): { target: string; external: boolean } {
  const fallback = { target: '/dashboard', external: false };
  if (!raw) return fallback;
  if (!/^https?:\/\//i.test(raw)) return { target: raw, external: false };
  try {
    const u = new URL(raw);
    return isExternalRedirectAllowed(u.hostname) ? { target: raw, external: true } : fallback;
  } catch {
    return fallback;
  }
}
/**
 * helper 가 본 PC 에 있어야 동작하는 페이지에서 제외할 경로.
 * - /login, /helper-install : helper 없이 진입 가능해야 다운로드 흐름 시작 가능.
 * - /chat : 모바일 PWA. backend API 만 사용 — helper 없는 환경 (모바일/외부 PC) 에서도 풀 동작.
 */
const HELPER_OPTIONAL_PATHS = new Set<string>(['/login', '/helper-install', '/chat']);

export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return;

  const auth = useAuthStore();
  const isPublic = PUBLIC_PATHS.has(to.path);

  // 2026-07-01 cookie 삭제 사고 fix — sessionStorage 만 검사하던 옛 로직이 cookie 삭제
  // 상태 (DevTools "Clear site data" / 다른 host cookie store / 만료) 를 감지 못 해
  // 사용자 화면은 dashboard 이지만 API 는 다 실패하는 유령 로그인 상태 발생. cookie
  // presence 확인 + 없으면 refresh 강제 시도 → 실패 시 clearUser + /login.
  if (auth.isAuthenticated && !isPublic) {
    const cookieRaw = (typeof document !== 'undefined' ? document.cookie : '') || '';
    const hasAccessCookie = /(?:^|;\s*)accessToken=/.test(cookieRaw);
    if (!hasAccessCookie) {
      const config = useRuntimeConfig();
      const baseURL = config.public.apiBase as string;
      let refreshOk = false;
      try {
        const res = await $fetch<{ result: number }>('/api/auth/refresh', {
          baseURL,
          method: 'POST',
          credentials: 'include',
        });
        refreshOk = res?.result === 0;
        clientLog('log', 'middleware:cookie-missing-refresh', { ok: refreshOk, path: to.fullPath });
      } catch (e) {
        clientLog('warn', 'middleware:cookie-missing-refresh:throw', { message: String((e as Error)?.message ?? e), path: to.fullPath });
      }
      if (!refreshOk) {
        auth.clearUser();
        return navigateTo({ path: '/login', query: { redirect: to.fullPath } });
      }
      // refresh 성공 → 아래 정상 path 로 통과 (cookie 재발급 완료).
    }
  }

  if (!auth.isAuthenticated && !isPublic) {
    // 2026-07-02 진단 gap fix — 옛에는 이 case (sessionStorage 없어 middleware 가 즉시
    // /login redirect) 에 clientLog 호출 없어서 backend stdout / DB 어디에도 흔적 안
    // 남는 사고. rc132 의 cookie-missing-refresh log 는 isAuthenticated=true case 만
    // 다뤘음. 사용자 밤새 로그아웃 사고의 진단 blindspot 이었음. hasCookie 는 HttpOnly
    // 라 값 자체는 안 보이지만 accessToken/refreshToken 라는 name 이 노출되지도 않으니
    // length 만 기록 (0 = 완전 삭제 / >0 = 어떤 cookie 존재).
    try {
      const cookieRaw = (typeof document !== 'undefined' ? document.cookie : '') || '';
      clientLog('warn', 'middleware:no-session-redirect', {
        path: to.fullPath,
        cookieLen: cookieRaw.length,
        hasNonHttpOnlyCookie: cookieRaw.length > 0,
      });
    } catch { /* clientLog fail — silent */ }
    return navigateTo({ path: '/login', query: { redirect: to.fullPath } });
  }
  if (auth.isAuthenticated && isPublic) {
    const r = resolveRedirect(to.query.redirect as string | undefined);
    return r.external ? navigateTo(r.target, { external: true }) : navigateTo(r.target);
  }

  // helper 미설치면 /helper-install 로 — 인증된 사용자가 helper 의존 페이지 진입 시.
  // 설치돼있으면 store 에 running/latest 동기화만 두고 진입 허용. 업데이트가 필요하면
  // default layout 의 배너가 사용자에게 알린다 (강제 X — B-2 정책).
  // dev 환경 (localhost frontend + prod-향 helper) 에서는 mismatch 로 false missing
  // 판정될 수 있어 helper check skip — dashboard 직접 진입 가능. prod build 영향 X.
  // 모바일 (UA 기반) 박혀있으면 helper check skip — 모바일은 127.0.0.1:30083 에 helper 없어
  // 항상 missing 판정 → /helper-install 무한 redirect 사고 회피. helper 의존 페이지 (대시보드 /
  // 터미널) 들어가도 helper 관련 UI 만 *비활성* 박힘 (강제 redirect X).
  const isMobile = typeof navigator !== 'undefined'
    && /iPhone|iPad|iPod|Android|Mobile/i.test(navigator.userAgent);
  if (auth.isAuthenticated && !HELPER_OPTIONAL_PATHS.has(to.path) && !import.meta.dev && !isMobile) {
    const helperVersion = useHelperVersionStore();
    await helperVersion.refresh();
    if (helperVersion.missing) {
      return navigateTo('/helper-install');
    }
  }

  // ROLE 가드 — 페이지 메타의 requiredRoles 와 사용자 role 매칭 (옵트인)
  const required = (to.meta as Record<string, unknown>)?.requiredRoles as string[] | undefined;
  if (auth.isAuthenticated && required && required.length > 0 && !required.includes(auth.role)) {
    return navigateTo('/dashboard');
  }
});
