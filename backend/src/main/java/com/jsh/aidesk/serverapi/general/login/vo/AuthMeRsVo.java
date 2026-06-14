package com.jsh.aidesk.serverapi.general.login.vo;

import java.time.OffsetDateTime;

import lombok.Data;

/** GET /api/auth/me 응답. */
@Data
public class AuthMeRsVo {
    private Long accountSn;
    private String loginId;
    private String displayName;
    private String role;
    private OffsetDateTime createdAt;
    private OffsetDateTime lastLoginDt;
}
