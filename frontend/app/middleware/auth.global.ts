import { defineNuxtRouteMiddleware, navigateTo } from '#app';
import { useAuthStore } from '~/stores/auth';
import { useHelperVersionStore } from '~/stores/helperVersion';

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
/** helper 가 본 PC 에 있어야 동작하는 페이지에서 제외할 경로 — 자기 자신 + login. */
const HELPER_OPTIONAL_PATHS = new Set<string>(['/login', '/helper-install']);

export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return;

  const auth = useAuthStore();
  const isPublic = PUBLIC_PATHS.has(to.path);

  if (!auth.isAuthenticated && !isPublic) {
    return navigateTo({ path: '/login', query: { redirect: to.fullPath } });
  }
  if (auth.isAuthenticated && isPublic) {
    const redirect = (to.query.redirect as string) || '/dashboard';
    return navigateTo(redirect);
  }

  // helper 미설치면 /helper-install 로 — 인증된 사용자가 helper 의존 페이지 진입 시.
  // 설치돼있으면 store 에 running/latest 동기화만 두고 진입 허용. 업데이트가 필요하면
  // default layout 의 배너가 사용자에게 알린다 (강제 X — B-2 정책).
  if (auth.isAuthenticated && !HELPER_OPTIONAL_PATHS.has(to.path)) {
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
