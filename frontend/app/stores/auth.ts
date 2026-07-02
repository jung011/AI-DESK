import { defineStore } from 'pinia';

const STORAGE_KEY = 'aidesk.auth';

interface AuthUser {
  accountSn: number;
  loginId: string;
  displayName: string;
  role: string;
}

interface AuthState {
  user: AuthUser | null;
}

/**
 * 인증 상태 — JWT 페이로드(accountSn / loginId / displayName / role) 를 라우트 가드/UI 에 노출.
 *
 * 토큰 자체는 HttpOnly 쿠키 (accessToken / refreshToken) 에 보관 → JS 접근 불가.
 * 본 store 는 식별 정보만 보관.
 *
 * 2026-07-02 sessionStorage → localStorage 전환 — 옛 sessionStorage 는 tab-scoped 라
 * 브라우저 tab 종료 / Chrome tab discard (메모리 부족 시) / 컴퓨터 재부팅 후 재개 시
 * clear 되어 middleware 가 사용자를 /login 로 강제 redirect 하는 밤새 로그아웃 사고
 * 유발. cookie (30일 Max-Age) 는 유지되어 실제 인증은 유효한데도. localStorage 는
 * 브라우저 재시작 후에도 persist → cookie 와 lifecycle 정합.
 *
 * 만료 정책 :
 *  - access 만료 시각은 store 가 보관하지 않는다. 만료 검증 책임은 BE 의 JwtAuthenticationFilter
 *    (401 ET 응답) 에 있고, FE 는 $api 인터셉터의 ET 분기에서 자동 refresh → 원 요청 재시도로 처리.
 *  - 따라서 hydrate 도 localStorage 의 user 를 그대로 복원. stale user 라도 첫 $api 호출이
 *    refresh 를 트리거해 갱신되거나, refresh 도 만료됐다면 인터셉터가 clearUser + /login 으로 정리.
 *
 * 보안 메모 : localStorage 의 role 은 클라가 변조 가능 → UI 인지 부조화 가능. 실제 권한 검증은
 *  BE 의 SecurityFilterChain.hasRole() 이 책임이라 ADMIN 액션은 403 NP 로 차단됨.
 */
export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
  }),

  getters: {
    isAuthenticated: (state): boolean => state.user !== null,
    loginId:     (state): string => state.user?.loginId ?? '',
    displayName: (state): string => state.user?.displayName ?? '',
    role:        (state): string => state.user?.role ?? '',
    accountSn:   (state): number | null => state.user?.accountSn ?? null,
  },

  actions: {
    setUser(user: AuthUser) {
      this.user = user;
      if (import.meta.client) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
      }
    },
    clearUser() {
      this.user = null;
      if (import.meta.client) {
        localStorage.removeItem(STORAGE_KEY);
      }
    },
    hydrate() {
      if (!import.meta.client) return;
      let raw = localStorage.getItem(STORAGE_KEY);
      // 2026-07-02 rc138 — 옛 sessionStorage 잔재 자동 migration.
      // rc137 (sessionStorage→localStorage 전환) 시 옛 로그인 세션의 sessionStorage
      // 값을 localStorage 로 옮기는 migration 없어 옛 사용자가 새 chunk 로드 시 auth
      // store 못 복원 → header 에 "게스트" 표시 → 로그아웃 인식 사고 재발. hydrate() 가
      // localStorage 비어있으면 sessionStorage fallback 검사 + 발견 시 자동 이관.
      if (!raw) {
        const legacy = sessionStorage.getItem(STORAGE_KEY);
        if (legacy) {
          raw = legacy;
          try { localStorage.setItem(STORAGE_KEY, legacy); } catch { /* quota 등 */ }
          try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
        }
      }
      if (!raw) return;
      try {
        this.user = JSON.parse(raw) as AuthUser;
      } catch {
        localStorage.removeItem(STORAGE_KEY);
        try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
      }
    },
  },
});
