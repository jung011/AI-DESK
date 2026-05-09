package com.jsh.aidesk.serverapi.messages.policy;

/**
 * 정책 검사 결과. accepted = true 면 그대로 발송, false 면 errorReason 으로 failed 처리.
 */
public record PolicyResult(boolean accepted, String errorReason) {

    public static PolicyResult accept() {
        return new PolicyResult(true, null);
    }

    public static PolicyResult reject(String reason) {
        return new PolicyResult(false, reason);
    }
}
