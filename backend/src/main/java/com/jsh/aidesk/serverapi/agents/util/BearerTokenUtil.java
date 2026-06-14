package com.jsh.aidesk.serverapi.agents.util;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.HexFormat;

import org.springframework.stereotype.Component;

/**
 * 외부 AI 의 Bearer token 생성/검증.
 *
 * <p>Token 형식: {@code aidesk_ext_<48자 hex>}. 192-bit entropy → brute force 불가능,
 * rainbow table 도 무의미 (모든 가능성 사전 계산 불가).
 *
 * <p>저장: raw token 의 SHA-256 hex digest 만 DB 에 둠 (deterministic). 호출자 token 도
 * 같은 방식으로 hash 후 DB 조회 — 매 요청 인덱스 lookup 1회.
 *
 * <p>raw token 은 발급 시점 1회만 호출자에게 반환. DB 유출 시에도 SHA-256 의 역연산
 * 불가능 + entropy 충분 → 실효적으로 안전. revoke = hash 컬럼 NULL.
 *
 * <p>BCrypt 같은 salt 기반 해시는 의도적으로 사용 안 함 — 매번 다른 hash 가 나와
 * 인덱스 lookup 이 불가능해진다.
 */
@Component
public class BearerTokenUtil {

    /** token prefix — 인증 layer 가 cookie JWT / agentId query 와 구분하는 마커. */
    public static final String TOKEN_PREFIX = "aidesk_ext_";

    /** raw token 의 hex 부분 길이 (= entropy bits / 4). 48 hex = 192 bits. */
    private static final int RAW_HEX_LEN = 48;

    private static final SecureRandom RNG = new SecureRandom();

    /** 새 raw Bearer token 생성. 호출자가 즉시 사용자에게 반환 + hash(raw) 와 함께 DB 저장. */
    public String generateRawToken() {
        byte[] bytes = new byte[RAW_HEX_LEN / 2];
        RNG.nextBytes(bytes);
        return TOKEN_PREFIX + HexFormat.of().formatHex(bytes);
    }

    /** Raw token 의 SHA-256 hex digest. DB 의 bearer_token_hash 컬럼에 저장. */
    public String hash(String rawToken) {
        if (rawToken == null) return null;
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(rawToken.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    /** raw token 이 우리 prefix 로 시작하는지 — 인증 분기에서 빠른 type 식별용. */
    public static boolean looksLikeBearerToken(String value) {
        return value != null && value.startsWith(TOKEN_PREFIX);
    }
}
