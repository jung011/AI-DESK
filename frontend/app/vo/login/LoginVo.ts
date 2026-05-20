/**
 * 인증 도메인 VO — backend 의 LoginVo / LoginAuthenticateRqVo / RsVo 와 1:1 매칭.
 *
 * 토큰 자체는 HttpOnly 쿠키로만 전달. 본 VO 의 응답은 식별 클레임만 노출.
 */

export interface LoginAuthenticateRqVo {
  loginId: string;
  password: string;
}

export interface LoginAuthenticateRsVo {
  accountSn: number;
  loginId: string;
  displayName: string;
  role: string;
}

export interface LoginSignupRqVo {
  loginId: string;
  password: string;
}

export interface LoginSignupRsVo {
  accountSn: number;
  loginId: string;
  displayName: string;
  role: string;
  createdAt: string;
}

export interface AuthMeRsVo {
  accountSn: number;
  loginId: string;
  displayName: string;
  role: string;
  createdAt: string;
  lastLoginDt: string | null;
}
