package com.jsh.aidesk.serverapi.general.login.vo;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class LoginAuthenticateRqVo {

    @NotBlank
    private String loginId;

    @NotBlank
    private String password;
}
