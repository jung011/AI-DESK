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
                                     int maxAgeSeconds, boolean secure) {
        StringBuilder sb = new StringBuilder();
        sb.append(name).append('=').append(value);
        sb.append("; Path=/");
        sb.append("; Max-Age=").append(maxAgeSeconds);
        sb.append("; HttpOnly");
        sb.append("; SameSite=Lax");
        if (secure) sb.append("; Secure");
        response.addHeader("Set-Cookie", sb.toString());
    }

    public static void clearAuthCookie(HttpServletResponse response, String name, boolean secure) {
        StringBuilder sb = new StringBuilder();
        sb.append(name).append('=');
        sb.append("; Path=/");
        sb.append("; Max-Age=0");
        sb.append("; HttpOnly");
        sb.append("; SameSite=Lax");
        if (secure) sb.append("; Secure");
        response.addHeader("Set-Cookie", sb.toString());
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
