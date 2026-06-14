package com.jsh.aidesk.serverapi.agents.security;

import java.io.IOException;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.util.BearerTokenUtil;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.common.jwt.AuthenticatedUser;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 외부 AI 의 Bearer token 인증 — Authorization: Bearer aidesk_ext_... 헤더 검증.
 *
 * <p>token prefix 가 우리 형식이 아닐 땐 통과 (cookie JWT 가 별도 filter 에서 처리).
 * 우리 prefix 일 때만 hash lookup → 매칭 시 SecurityContext 에 owner_account_sn 기준
 * AuthenticatedUser 박아둠. 기존 service 의 AuthContext.currentAccountSn() 코드 그대로 동작.
 *
 * <p>외부 AI 식별자 (agent_id) 는 request attribute {@link #ATTR_EXTERNAL_AGENT_ID} 에
 * 저장 — message sender 식별 등 필요 시 controller 가 꺼낼 수 있음.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class BearerTokenAuthenticationFilter extends OncePerRequestFilter {

    public static final String ATTR_EXTERNAL_AGENT_ID = "aidesk.external.agentId";

    private final AgentMapper agentMapper;
    private final BearerTokenUtil tokenUtil;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                     FilterChain filterChain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            filterChain.doFilter(request, response);
            return;
        }
        String rawToken = header.substring("Bearer ".length()).trim();
        if (!BearerTokenUtil.looksLikeBearerToken(rawToken)) {
            // 다른 Bearer token (혹시 미래 OAuth 등) 은 그대로 통과 — 우리 책임 아님.
            filterChain.doFilter(request, response);
            return;
        }

        String hash = tokenUtil.hash(rawToken);
        AgentVo agent = agentMapper.selectByBearerTokenHash(hash);
        if (agent == null) {
            log.warn("[bearer-auth] reject — token not found (path={})", request.getRequestURI());
            filterChain.doFilter(request, response);   // SecurityContext 비어있음 → entry-point 가 401
            return;
        }

        // owner 기준 인증 — service 의 AuthContext.currentAccountSn() 가 owner 반환.
        AuthenticatedUser principal = new AuthenticatedUser(
                "external:" + agent.getAgentId(),
                agent.getOwnerAccountSn(),
                "EXTERNAL"
        );
        var authToken = new UsernamePasswordAuthenticationToken(
                principal, null, AuthorityUtils.NO_AUTHORITIES);
        authToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
        SecurityContext ctx = SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(authToken);
        SecurityContextHolder.setContext(ctx);
        request.setAttribute(ATTR_EXTERNAL_AGENT_ID, agent.getAgentId());

        filterChain.doFilter(request, response);
    }
}
