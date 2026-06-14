package com.jsh.aidesk.serverapi.agents.vo;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.ToString;

/**
 * 외부 AI 의 token 발급/rotate 응답.
 * <p>{@link #token} 은 *발급 시점 1회만* 호출자에게 노출됨 — DB 에는 SHA-256 hash 만 저장돼
 * 이후 복원 불가. 사용자는 즉시 외부 service 의 환경변수에 박아야 한다.
 */
@Getter
@AllArgsConstructor
@ToString
public class ExternalAgentTokenRsVo {

    private final String agentId;
    private final String agentName;
    /** raw Bearer token. 응답 직후 안전한 곳에 저장 — 이후 복원 불가. */
    private final String token;
}
