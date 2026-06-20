import { useAuthStore } from '~/stores/auth';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type {
  LoginAuthenticateRqVo,
  LoginAuthenticateRsVo,
  LoginSignupRqVo,
  LoginSignupRsVo,
  AuthMeRsVo,
} from '~/vo/login/LoginVo';

/**
 * 인증 동작 wrapper — signIn / signOut / signup / refreshMe.
 *
 * 토큰은 HttpOnly cookie 라 JS 가 못 읽음. signIn 응답 body 의 식별 클레임만 store 에 set.
 */
export const useAuth = () => {
  const { $api } = useNuxtApp();
  const auth = useAuthStore();

  const signIn = async (rq: LoginAuthenticateRqVo): Promise<LoginAuthenticateRsVo> => {
    const env = await $api<ApiEnvelope<LoginAuthenticateRsVo>>('/api/auth/authenticate', {
      method: 'POST',
      body: rq,
    });
    if (env.result !== 0) {
      throw new Error('이메일 또는 비밀번호가 올바르지 않습니다.');
    }
    auth.setUser({
      accountSn: env.data.accountSn,
      loginId: env.data.loginId,
      displayName: env.data.displayName,
      role: env.data.role,
    });
    return env.data;
  };

  const signOut = async () => {
    try {
      await $api<ApiEnvelope<number>>('/api/auth/sign-out', { method: 'POST' });
    } finally {
      auth.clearUser();
    }
  };

  /** 운영자 도구가 호출하는 회원가입. 페이지 X — 함수만 제공. */
  const signup = async (rq: LoginSignupRqVo): Promise<LoginSignupRsVo> => {
    const env = await $api<ApiEnvelope<LoginSignupRsVo>>('/api/auth/signup', {
      method: 'POST',
      body: rq,
    });
    if (env.result !== 0) {
      throw new Error(env.message || '회원가입 실패');
    }
    return env.data;
  };

  /** 현재 사용자 조회. store 도 동기화. 토큰 만료/위조 시 throw. */
  const refreshMe = async (): Promise<AuthMeRsVo> => {
    const env = await $api<ApiEnvelope<AuthMeRsVo>>('/api/auth/me');
    if (env.result !== 0) {
      throw new Error(env.message || 'me 조회 실패');
    }
    auth.setUser({
      accountSn: env.data.accountSn,
      loginId: env.data.loginId,
      displayName: env.data.displayName,
      role: env.data.role,
    });
    return env.data;
  };

  return { signIn, signOut, signup, refreshMe };
};
