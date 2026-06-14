package com.jsh.aidesk.serverapi.common.jwt;

import lombok.Getter;

@Getter
public class JwtValidationResult {

    public enum Status {
        VALID,
        EXPIRED,
        INVALID
    }

    private final Status status;
    private final String loginId;
    private final Long accountSn;
    private final String role;
    private final String jti;

    private JwtValidationResult(Status status, String loginId, Long accountSn, String role, String jti) {
        this.status = status;
        this.loginId = loginId;
        this.accountSn = accountSn;
        this.role = role;
        this.jti = jti;
    }

    public static JwtValidationResult valid(String loginId, Long accountSn, String role, String jti) {
        return new JwtValidationResult(Status.VALID, loginId, accountSn, role, jti);
    }

    public static JwtValidationResult expired() {
        return new JwtValidationResult(Status.EXPIRED, null, null, null, null);
    }

    public static JwtValidationResult invalid() {
        return new JwtValidationResult(Status.INVALID, null, null, null, null);
    }
}
