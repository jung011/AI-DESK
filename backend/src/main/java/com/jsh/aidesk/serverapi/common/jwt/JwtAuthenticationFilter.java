package com.jsh.aidesk.serverapi.common.jwt;

import com.jsh.aidesk.serverapi.common.util.CookieUtil;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * 매 요청마다 access token 쿠키를 검증해 SecurityContext 를 세팅한다.
 * 만료/위조 토큰은 SecurityContext 미세팅 상태로 통과 → SecurityConfig 의 entry-point 가 401/403 처리.
 * 단 EXPIRED 인 경우는 즉시 401 ET 응답 — 클라이언트 axios 인터셉터가 이 코드로 자동 refresh 시도.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtProvider jwtProvider;

    private static final String[] PUBLIC_PATH_PREFIXES = {
            "/api/auth/authenticate",
            "/api/auth/refresh",
            "/api/auth/signup",
            "/swagger-ui",
            "/v3/api-docs"
    };

    private boolean isPublicPath(String path) {
        for (String prefix : PUBLIC_PATH_PREFIXES) {
            if (path.startsWith(prefix)) return true;
        }
        return false;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain) throws ServletException, IOException {

        String token = CookieUtil.readCookie(request, CookieUtil.ACCESS_TOKEN_COOKIE);
        if (token == null) {
            filterChain.doFilter(request, response);
            return;
        }

        JwtValidationResult result = jwtProvider.validate(token);

        if (result.getStatus() == JwtValidationResult.Status.EXPIRED) {
            if (isPublicPath(request.getRequestURI())) {
                filterChain.doFilter(request, response);
                return;
            }
            writeErrorResponse(response, HttpServletResponse.SC_UNAUTHORIZED, "ET", "Expired token");
            return;
        }

        if (result.getStatus() == JwtValidationResult.Status.INVALID) {
            filterChain.doFilter(request, response);
            return;
        }

        AuthenticatedUser principal = new AuthenticatedUser(
                result.getLoginId(), result.getAccountSn(), result.getRole());

        AbstractAuthenticationToken authenticationToken = new UsernamePasswordAuthenticationToken(
                principal, null, AuthorityUtils.createAuthorityList("ROLE_" + result.getRole()));
        authenticationToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

        SecurityContext securityContext = SecurityContextHolder.createEmptyContext();
        securityContext.setAuthentication(authenticationToken);
        SecurityContextHolder.setContext(securityContext);

        filterChain.doFilter(request, response);
    }

    private void writeErrorResponse(HttpServletResponse response, int status, String code, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(String.format("{\"code\":\"%s\",\"message\":\"%s\"}", code, message));
    }
}
