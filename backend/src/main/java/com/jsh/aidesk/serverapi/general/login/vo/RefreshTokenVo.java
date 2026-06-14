package com.jsh.aidesk.serverapi.general.login.vo;

import lombok.Data;

import java.time.OffsetDateTime;

@Data
public class RefreshTokenVo {
    private String jti;
    private Long accountSn;
    private String loginId;
    private String familyId;
    private String tokenHash;
    private String revokedYn;
    private OffsetDateTime expiresAt;
    private OffsetDateTime createdAt;
}
