package com.jsh.aidesk.serverapi.general.login.vo;

import java.time.OffsetDateTime;

import lombok.Data;

/**
 * 사용자 계정 VO (t_user) — 인증 + 조회 + insert 공통 캐리어.
 *
 * 컬럼 매핑은 LoginMapper.xml 참조. 다른 도메인이 user 식별만 쓸 거면 AuthenticatedUser 를 본다.
 */
@Data
public class LoginVo {

    private Long accountSn;
    private String loginId;
    private String password;
    private String displayName;
    private String role;
    private OffsetDateTime lastLoginDt;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
