package com.jsh.aidesk.serverapi.common.jwt;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * SecurityContext 의 principal — JwtAuthenticationFilter 가 세팅한다.
 */
@Getter
@RequiredArgsConstructor
public class AuthenticatedUser {
    private final String loginId;
    private final Long accountSn;
    private final String role;
}
