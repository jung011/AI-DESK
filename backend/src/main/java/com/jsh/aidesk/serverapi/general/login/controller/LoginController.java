package com.jsh.aidesk.serverapi.general.login.controller;

import com.jsh.aidesk.serverapi.common.jwt.AuthenticatedUser;
import com.jsh.aidesk.serverapi.common.jwt.JwtProvider;
import com.jsh.aidesk.serverapi.common.jwt.JwtValidationResult;
import com.jsh.aidesk.serverapi.common.response.ResponseCode;
import com.jsh.aidesk.serverapi.common.response.ResponseJson;
import com.jsh.aidesk.serverapi.common.util.CookieUtil;
import com.jsh.aidesk.serverapi.common.util.HashUtil;
import com.jsh.aidesk.serverapi.general.login.service.LoginService;
import com.jsh.aidesk.serverapi.general.login.vo.AuthMeRsVo;
import com.jsh.aidesk.serverapi.general.login.vo.LoginAuthenticateRqVo;
import com.jsh.aidesk.serverapi.general.login.vo.LoginAuthenticateRsVo;
import com.jsh.aidesk.serverapi.general.login.vo.LoginSignupRqVo;
import com.jsh.aidesk.serverapi.general.login.vo.LoginSignupRsVo;
import com.jsh.aidesk.serverapi.general.login.vo.LoginVo;
import com.jsh.aidesk.serverapi.general.login.vo.RefreshTokenVo;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Slf4j
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class LoginController {

    private final LoginService loginService;
    private final JwtProvider jwtProvider;

    /** prod HTTPS 환경에서는 true 로 — 쿠키에 Secure 플래그 부여. dev 는 기본 false. */
    @Value("${cookie.secure:false}")
    private boolean cookieSecure;

    /**
     * subdomain 공유를 위한 cookie Domain 속성. 예: ".example.com".
     * 미설정 (빈 값) = 옛 host-only 동작 — 로컬 dev 호환.
     * 외부화: 다음 우선순위로 읽음 — application.yml `cookie.domain` > env `COOKIE_DOMAIN` (Spring relaxed binding) > env `AIDESK_COOKIE_DOMAIN` (명시 fallback).
     * `AIDESK_*` prefix env 는 Spring 이 `aidesk.cookie.domain` property 로 매핑하므로 `cookie.domain` 과 충돌 X — 명시 fallback 으로 직접 읽음.
     */
    @Value("${cookie.domain:${AIDESK_COOKIE_DOMAIN:}}")
    private String cookieDomain;

    /** 회원가입 — API only (페이지 없음). 1단계 비인증 호출 허용. */
    @PostMapping("/signup")
    public ResponseJson<LoginSignupRsVo> signup(@RequestBody @Valid LoginSignupRqVo rq) {
        LoginVo created = loginService.signup(rq.getLoginId(), rq.getPassword());
        if (created == null) {
            return ResponseJson.fail(ResponseCode.FAIL_DUPLICATE);
        }
        LoginSignupRsVo rs = new LoginSignupRsVo();
        rs.setAccountSn(created.getAccountSn());
        rs.setLoginId(created.getLoginId());
        rs.setDisplayName(created.getDisplayName());
        rs.setRole(created.getRole());
        rs.setCreatedAt(created.getCreatedAt());
        return ResponseJson.ok(rs);
    }

    /** 로그인 — access + refresh 쿠키 발급 + 식별 클레임 body. */
    @PostMapping("/authenticate")
    public ResponseJson<LoginAuthenticateRsVo> authenticate(
            @RequestBody @Valid LoginAuthenticateRqVo rq,
            HttpServletResponse response) {

        LoginVo lookup = new LoginVo();
        lookup.setLoginId(rq.getLoginId().trim().toLowerCase());
        lookup.setPassword(rq.getPassword());

        LoginVo account = loginService.authenticate(lookup);
        if (account == null) {
            return ResponseJson.fail(ResponseCode.FAIL_AUTH);
        }

        loginService.recordLastLogin(account.getAccountSn());

        String accessToken = jwtProvider.createAccessToken(
                account.getLoginId(), account.getAccountSn(), account.getRole());
        String refreshToken = loginService.issueNewRefreshToken(account);

        // access 쿠키 Max-Age 를 refresh 만료와 동일하게 — JWT 자체는 access 만료 시점에 끊기지만
        // 쿠키가 살아있어야 만료 토큰이 BE 에 도달해 ET 응답 → axios 자동 refresh 시도 가능.
        CookieUtil.setAuthCookie(response, CookieUtil.ACCESS_TOKEN_COOKIE,
                accessToken, jwtProvider.getRefreshExpirationSeconds(), cookieSecure, cookieDomain);
        CookieUtil.setAuthCookie(response, CookieUtil.REFRESH_TOKEN_COOKIE,
                refreshToken, jwtProvider.getRefreshExpirationSeconds(), cookieSecure, cookieDomain);

        LoginAuthenticateRsVo rs = new LoginAuthenticateRsVo();
        rs.setAccountSn(account.getAccountSn());
        rs.setLoginId(account.getLoginId());
        rs.setDisplayName(account.getDisplayName());
        rs.setRole(account.getRole());
        return ResponseJson.ok(rs);
    }

    /**
     * 리프레시 토큰 회전 — 옛 jti 폐기 + 동일 family 의 새 토큰 발급.
     * reuse 감지 시 family 전체 폐기 후 401.
     */
    @PostMapping("/refresh")
    public ResponseJson<LoginAuthenticateRsVo> refresh(
            HttpServletRequest request, HttpServletResponse response) {

        String refreshToken = CookieUtil.readCookie(request, CookieUtil.REFRESH_TOKEN_COOKIE);
        if (refreshToken == null) {
            return ResponseJson.fail(ResponseCode.FAIL_TOKEN);
        }

        JwtValidationResult result = jwtProvider.validate(refreshToken);
        if (result.getStatus() != JwtValidationResult.Status.VALID) {
            return ResponseJson.fail(ResponseCode.FAIL_TOKEN);
        }

        String jti = result.getJti();
        if (jti == null) {
            return ResponseJson.fail(ResponseCode.FAIL_TOKEN);
        }

        RefreshTokenVo stored = loginService.getRefreshTokenByJti(jti);
        if (stored == null) {
            return ResponseJson.fail(ResponseCode.FAIL_TOKEN);
        }

        if ("Y".equals(stored.getRevokedYn())) {
            log.warn("Refresh token reuse detected: loginId={} family={}",
                    stored.getLoginId(), stored.getFamilyId());
            loginService.revokeFamily(stored.getLoginId(), stored.getFamilyId());
            return ResponseJson.fail(ResponseCode.FAIL_TOKEN);
        }

        if (!HashUtil.sha256(refreshToken).equals(stored.getTokenHash())) {
            return ResponseJson.fail(ResponseCode.FAIL_TOKEN);
        }

        LoginVo account = loginService.getActiveAccountBySn(stored.getAccountSn());
        if (account == null) {
            return ResponseJson.fail(ResponseCode.FAIL_TOKEN);
        }

        String newRefreshToken = loginService.rotateRefreshToken(account, jti, stored.getFamilyId());
        String newAccessToken = jwtProvider.createAccessToken(
                account.getLoginId(), account.getAccountSn(), account.getRole());

        CookieUtil.setAuthCookie(response, CookieUtil.ACCESS_TOKEN_COOKIE,
                newAccessToken, jwtProvider.getRefreshExpirationSeconds(), cookieSecure, cookieDomain);
        CookieUtil.setAuthCookie(response, CookieUtil.REFRESH_TOKEN_COOKIE,
                newRefreshToken, jwtProvider.getRefreshExpirationSeconds(), cookieSecure, cookieDomain);

        LoginAuthenticateRsVo rs = new LoginAuthenticateRsVo();
        rs.setAccountSn(account.getAccountSn());
        rs.setLoginId(account.getLoginId());
        rs.setDisplayName(account.getDisplayName());
        rs.setRole(account.getRole());
        return ResponseJson.ok(rs);
    }

    /** 로그아웃 — refresh family 전체 삭제 + 쿠키 clear. */
    @PostMapping("/sign-out")
    public ResponseJson<Integer> signOut(
            @AuthenticationPrincipal AuthenticatedUser principal,
            HttpServletResponse response) {
        if (principal != null && principal.getLoginId() != null) {
            loginService.deleteAllRefreshTokens(principal.getLoginId());
        }
        CookieUtil.clearAuthCookie(response, CookieUtil.ACCESS_TOKEN_COOKIE, cookieSecure, cookieDomain);
        CookieUtil.clearAuthCookie(response, CookieUtil.REFRESH_TOKEN_COOKIE, cookieSecure, cookieDomain);
        return ResponseJson.ok(ResponseCode.SUCCESS);
    }

    /** 현재 사용자 정보 — 토큰 검증 후 본인 row 조회. */
    @GetMapping("/me")
    public ResponseJson<AuthMeRsVo> me(@AuthenticationPrincipal AuthenticatedUser principal) {
        if (principal == null) {
            return ResponseJson.fail(ResponseCode.FAIL_UNAUTHORIZED);
        }
        LoginVo account = loginService.getActiveAccountBySn(principal.getAccountSn());
        if (account == null) {
            return ResponseJson.fail(ResponseCode.FAIL_UNAUTHORIZED);
        }
        AuthMeRsVo rs = new AuthMeRsVo();
        rs.setAccountSn(account.getAccountSn());
        rs.setLoginId(account.getLoginId());
        rs.setDisplayName(account.getDisplayName());
        rs.setRole(account.getRole());
        rs.setCreatedAt(account.getCreatedAt());
        rs.setLastLoginDt(account.getLastLoginDt());
        return ResponseJson.ok(rs);
    }
}
