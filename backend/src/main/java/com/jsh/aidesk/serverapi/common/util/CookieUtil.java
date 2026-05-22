package com.jsh.aidesk.serverapi.common.util;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * 인증 쿠키 유틸 — HttpOnly + SameSite=Lax (+ Secure when secure=true).
 * secure 플래그는 호출자(LoginController) 가 prod profile / cookie.secure 설정으로 전달.
 */
public final class CookieUtil {

    public static final String ACCESS_TOKEN_COOKIE = "accessToken";
    public static final String REFRESH_TOKEN_COOKIE = "refreshToken";

    private CookieUtil() {}

    public static void setAuthCookie(HttpServletResponse response, String name, String value,
                                     int maxAgeSeconds, boolean secure, String domain) {
        StringBuilder sb = new StringBuilder();
        sb.append(name).append('=').append(value);
        sb.append("; Path=/");
        sb.append("; Max-Age=").append(maxAgeSeconds);
        sb.append("; HttpOnly");
        sb.append("; SameSite=Lax");
        if (secure) sb.append("; Secure");
        if (domain != null && !domain.isBlank()) sb.append("; Domain=").append(domain);
        response.addHeader("Set-Cookie", sb.toString());

        // Cookie 충돌 방지 — domain 명시 발급 시 host-only 잔재 cookie 가 같이 살아남아 first-match
        // 으로 잘못 채택되는 silent failure 회피를 위해 host-only 변형도 Max-Age=0 으로 cleanup.
        // RFC 6265 상 같은 이름이라도 Domain 이 다르면 별개 cookie 라 명시 expire 가 필요.
        if (domain != null && !domain.isBlank()) {
            response.addHeader("Set-Cookie", buildExpireHeader(name, secure, null));
        }
    }

    public static void clearAuthCookie(HttpServletResponse response, String name,
                                       boolean secure, String domain) {
        response.addHeader("Set-Cookie", buildExpireHeader(name, secure, domain));
        // 동일 이유로 logout/clear 시에도 host-only 잔재까지 함께 expire.
        if (domain != null && !domain.isBlank()) {
            response.addHeader("Set-Cookie", buildExpireHeader(name, secure, null));
        }
    }

    private static String buildExpireHeader(String name, boolean secure, String domain) {
        StringBuilder sb = new StringBuilder();
        sb.append(name).append('=');
        sb.append("; Path=/");
        sb.append("; Max-Age=0");
        sb.append("; HttpOnly");
        sb.append("; SameSite=Lax");
        if (secure) sb.append("; Secure");
        if (domain != null && !domain.isBlank()) sb.append("; Domain=").append(domain);
        return sb.toString();
    }

    public static String readCookie(HttpServletRequest request, String name) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) return null;
        for (Cookie c : cookies) {
            if (name.equals(c.getName())) return c.getValue();
        }
        return null;
    }
}
