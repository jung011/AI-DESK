package com.jsh.aidesk.serverapi.general.login.vo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 회원가입 요청 — 페이지 없음 (API only).
 * displayName/role 은 받지 않음. 서버가 loginId 값을 display_name 에 자동 세팅, role='USER' 기본.
 */
@Data
public class LoginSignupRqVo {

    @NotBlank
    @Email
    private String loginId;

    @NotBlank
    @Size(min = 8, max = 72)
    private String password;
}
