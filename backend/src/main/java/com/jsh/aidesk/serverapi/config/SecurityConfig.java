package com.jsh.aidesk.serverapi.config;

import com.jsh.aidesk.serverapi.agents.security.BearerTokenAuthenticationFilter;
import com.jsh.aidesk.serverapi.common.jwt.JwtAuthenticationFilter;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

import java.io.IOException;

/**
 * Spring Security 설정 — STATELESS + JWT 필터.
 * PUBLIC : /api/auth/authenticate, /api/auth/refresh, /api/auth/signup, /api/health, swagger.
 * helper 보고용 /api/desktop/** 는 임시 비인증 허용 (helper-user binding 단계에서 재정의).
 * 그 외 모든 /api/** 는 인증 필요.
 */
@RequiredArgsConstructor
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final BearerTokenAuthenticationFilter bearerTokenAuthenticationFilter;

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    protected SecurityFilterChain configure(HttpSecurity http) throws Exception {

        http
            .cors(cors -> {})
            .csrf(auth -> auth.disable())
            .httpBasic(auth -> auth.disable())
            .formLogin(form -> form.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        "/",
                        // Spring Boot 가 controller 의 ResponseStatusException 을 /error 로 forward.
                        // 비인증 호출(/api/messages 의 cross-user 403 등) 이 여기로 들어와 401 NA
                        // 로 변환되지 않도록 permitAll.
                        "/error",
                        "/api/auth/authenticate",
                        "/api/auth/refresh",
                        "/api/auth/signup",
                        "/api/health",
                        "/swagger-ui/**",
                        "/v3/api-docs/**"
                ).permitAll()
                .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                // helper 보고용 endpoint — 임시 비인증 허용. 후속 helper-user binding 단계에서 별도 인증.
                .requestMatchers("/api/desktop/**").permitAll()
                // 외부 AI CRUD + token 발급 — 본인 user 의 쿠키 JWT 필수.
                .requestMatchers("/api/agents/external/**").authenticated()
                // aidesk-channel mcp 가 외부 터미널의 claude 안에서 호출 — 쿠키/토큰 없이 fetch.
                // 비인증 허용 + service 가 sender_agent_id 의 owner 로 user 컨텍스트 fallback.
                .requestMatchers("/api/agents/**").permitAll()
                .requestMatchers("/api/messages/**").permitAll()
                // Frontend ↔ Backend WebSocket — handshake 단계 JwtAuthenticationFilter 가 cookie 검증
                // + JwtHandshakeInterceptor 가 AuthenticatedUser 없으면 거부. 여기선 permit + interceptor 위임.
                .requestMatchers("/ws/messages").permitAll()
                .requestMatchers("/api/auth/sign-out").authenticated()
                .anyRequest().authenticated()
            )
            .exceptionHandling(exception -> exception
                .authenticationEntryPoint(new FailedAuthenticationEntryPoint())
                .accessDeniedHandler(new ForbiddenAccessDeniedHandler())
            );

        http
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
            // cookie JWT 다음 — Authorization: Bearer aidesk_ext_... 검증. cookie 인증된 사용자엔
            // 영향 없음 (SecurityContext 이미 set). cookie 없는 외부 AI 만 본 filter 가 인증 부여.
            .addFilterAfter(bearerTokenAuthenticationFilter, JwtAuthenticationFilter.class);

        return http.build();
    }
}

class FailedAuthenticationEntryPoint implements AuthenticationEntryPoint {
    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response,
                         AuthenticationException authException) throws IOException, ServletException {
        response.setContentType("application/json");
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.getWriter().write("{\"code\":\"NA\",\"message\":\"Not authenticated\"}");
    }
}

class ForbiddenAccessDeniedHandler implements AccessDeniedHandler {
    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException, ServletException {
        response.setContentType("application/json");
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.getWriter().write("{\"code\":\"NP\",\"message\":\"Do not have permission\"}");
    }
}
