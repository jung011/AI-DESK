package com.jsh.aidesk.serverapi.common.jwt;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.annotation.PostConstruct;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;

/**
 * JWT 액세스/리프레시 토큰 생성/검증.
 *
 * 액세스: 짧은 만료(분 단위 또는 1h dev), payload sub=loginId / accountSn / role.
 * 리프레시: 긴 만료(7일), payload sub + jti. 회전 시 jti 변경.
 */
@Slf4j
@Component
public class JwtProvider {

    @Value("${jwt.secret-key}")
    private String secretKeyString;

    @Getter
    @Value("${jwt.access-expiration-seconds}")
    private int accessExpirationSeconds;

    @Getter
    @Value("${jwt.refresh-expiration-seconds}")
    private int refreshExpirationSeconds;

    private SecretKey secretKey;

    @PostConstruct
    void init() {
        byte[] bytes = secretKeyString.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32) {
            throw new IllegalStateException(
                    "jwt.secret-key must be at least 32 bytes for HS256, got " + bytes.length);
        }
        this.secretKey = Keys.hmacShaKeyFor(bytes);
    }

    public String createAccessToken(String loginId, Long accountSn, String role) {
        Date expiredDate = Date.from(Instant.now().plus(accessExpirationSeconds, ChronoUnit.SECONDS));
        return Jwts.builder()
                .setSubject(loginId)
                .claim("accountSn", accountSn)
                .claim("role", role)
                .setIssuedAt(new Date())
                .setExpiration(expiredDate)
                .signWith(secretKey)
                .compact();
    }

    public String createRefreshToken(String loginId, String jti) {
        Date expiredDate = Date.from(Instant.now().plus(refreshExpirationSeconds, ChronoUnit.SECONDS));
        return Jwts.builder()
                .setSubject(loginId)
                .setId(jti)
                .setIssuedAt(new Date())
                .setExpiration(expiredDate)
                .signWith(secretKey)
                .compact();
    }

    public JwtValidationResult validate(String jwt) {
        try {
            Claims claims = Jwts.parserBuilder()
                    .setSigningKey(secretKey)
                    .build()
                    .parseClaimsJws(jwt)
                    .getBody();
            String loginId = claims.getSubject();
            Long accountSn = claims.get("accountSn", Long.class);
            String role = claims.get("role", String.class);
            return JwtValidationResult.valid(loginId, accountSn, role, claims.getId());
        } catch (ExpiredJwtException e) {
            return JwtValidationResult.expired();
        } catch (Exception e) {
            log.warn("Invalid JWT token: {}", e.getClass().getSimpleName());
            return JwtValidationResult.invalid();
        }
    }
}
