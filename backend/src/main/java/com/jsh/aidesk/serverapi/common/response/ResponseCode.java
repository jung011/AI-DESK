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
    FAIL_POLICY(1, "Policy rejected the request.");

    private final int code;
    private final String message;
}
