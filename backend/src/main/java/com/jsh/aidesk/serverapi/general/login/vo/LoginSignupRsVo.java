package com.jsh.aidesk.serverapi.general.login.vo;

import java.time.OffsetDateTime;

import lombok.Data;

@Data
public class LoginSignupRsVo {
    private Long accountSn;
    private String loginId;
    private String displayName;
    private String role;
    private OffsetDateTime createdAt;
}
