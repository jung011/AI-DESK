import { defineStore } from 'pinia';
import { authDebug } from '~/utils/authDebug';

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
 * 만료 정책 :
 *  - access 만료 시각은 store 가 보관하지 않는다. 만료 검증 책임은 BE 의 JwtAuthenticationFilter
 *    (401 ET 응답) 에 있고, FE 는 $api 인터셉터의 ET 분기에서 자동 refresh → 원 요청 재시도로 처리.
 *  - 따라서 hydrate 도 sessionStorage 의 user 를 그대로 복원. stale user 라도 첫 $api 호출이
 *    refresh 를 트리거해 갱신되거나, refresh 도 만료됐다면 인터셉터가 clearUser + /login 으로 정리.
 *
 * 보안 메모 : sessionStorage 의 role 은 클라가 변조 가능 → UI 인지 부조화 가능. 실제 권한 검증은
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
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
        authDebug('log', 'setUser', { accountSn: user.accountSn, loginId: user.loginId });
      }
    },
    clearUser() {
      if (import.meta.client) {
        authDebug('error', 'clearUser called', {
          prevUser: this.user ? { accountSn: this.user.accountSn, loginId: this.user.loginId } : null,
          location: window.location.href,
          stack: new Error('clearUser stack').stack,
        });
      }
      this.user = null;
      if (import.meta.client) {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    },
    hydrate() {
      if (!import.meta.client) return;
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) {
        authDebug('log', 'hydrate — no sessionStorage entry');
        return;
      }
      try {
        this.user = JSON.parse(raw) as AuthUser;
        authDebug('log', 'hydrate ok', { accountSn: this.user?.accountSn });
      } catch {
        sessionStorage.removeItem(STORAGE_KEY);
        authDebug('error', 'hydrate parse fail — sessionStorage cleared');
      }
    },
  },
});
