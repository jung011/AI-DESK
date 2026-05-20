package com.jsh.aidesk.serverapi.general.login.vo;

import lombok.Data;

/**
 * 로그인/refresh 응답.
 *
 * 보안 메모: access JWT 자체는 HttpOnly 쿠키로만 전달. 응답 body 에는 페이로드 클레임 일부만 노출해
 * FE 가 디코드 없이 user state 를 갱신할 수 있게 한다 (XSS 시 토큰 탈취 차단).
 */
@Data
public class LoginAuthenticateRsVo {
    private Long accountSn;
    private String loginId;
    private String displayName;
    private String role;
}
