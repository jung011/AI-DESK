package com.jsh.aidesk.serverapi.common.response;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

@Getter
@RequiredArgsConstructor
public enum ResponseCode implements CodeData {

    SUCCESS(0, "OK"),
    FAIL_REGIST(1, "Data registration failed."),
    FAIL_UPDATE(1, "Data update failed."),
    FAIL_DELETE(1, "Data delete failed."),
    FAIL_NOT_FOUND(1, "Data not found."),
    FAIL_VALIDATION(1, "Validation failed."),
    FAIL_POLICY(1, "Policy rejected the request."),
    FAIL_AUTH(1, "이메일 또는 비밀번호가 올바르지 않습니다."),
    FAIL_TOKEN(1, "Invalid or expired token."),
    FAIL_DUPLICATE(1, "이미 가입된 이메일입니다."),
    FAIL_UNAUTHORIZED(1, "Unauthorized.");

    private final int code;
    private final String message;
}
