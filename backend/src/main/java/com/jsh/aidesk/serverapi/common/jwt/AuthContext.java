package com.jsh.aidesk.serverapi.common.jwt;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * SecurityContext 에서 현재 사용자 식별자를 꺼내는 static helper.
 * 멀티유저 격리가 필요한 service 가 호출.
 *
 * 인증되지 않은 호출자에서 currentAccountSn() 부르면 IllegalStateException — 보호 경로는
 * SecurityConfig 의 anyRequest().authenticated() 가 막아야 정상.
 */
public final class AuthContext {

    private AuthContext() {}

    /** 현재 사용자의 account_sn. 인증되지 않았으면 throw. */
    public static Long currentAccountSn() {
        AuthenticatedUser u = currentUserOrNull();
        if (u == null) {
            throw new IllegalStateException("not authenticated — SecurityConfig 가 비인증 호출을 막아야 한다");
        }
        return u.getAccountSn();
    }

    /** 현재 사용자의 loginId. 없으면 throw. */
    public static String currentLoginId() {
        AuthenticatedUser u = currentUserOrNull();
        if (u == null) {
            throw new IllegalStateException("not authenticated");
        }
        return u.getLoginId();
    }

    /** 인증된 사용자가 있으면 반환, 없으면 null — helper /api/desktop/** 같은 비인증 경로용. */
    public static AuthenticatedUser currentUserOrNull() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) return null;
        if (auth.getPrincipal() instanceof AuthenticatedUser u) return u;
        return null;
    }

    public static boolean isAuthenticated() {
        return currentUserOrNull() != null;
    }
}
