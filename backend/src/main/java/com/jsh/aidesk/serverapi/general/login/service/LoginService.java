package com.jsh.aidesk.serverapi.general.login.service;

import com.jsh.aidesk.serverapi.general.login.vo.LoginVo;
import com.jsh.aidesk.serverapi.general.login.vo.RefreshTokenVo;

public interface LoginService {

    /**
     * 자격증명 검증. 성공 시 계정 정보 반환, 실패 시 null.
     */
    LoginVo authenticate(LoginVo vo);

    /** 활성 계정을 SN 으로 조회 (refresh / me 흐름에서 사용). */
    LoginVo getActiveAccountBySn(Long accountSn);

    /** 새 사용자 등록 (signup). loginId 정규화 + BCrypt 해시 + insert.
     *  중복이면 null. 성공 시 generated accountSn 포함한 LoginVo 반환. */
    LoginVo signup(String loginId, String rawPassword);

    /** 새로운 family 의 리프레시 토큰 발급, JWT 문자열 반환. */
    String issueNewRefreshToken(LoginVo account);

    /** 리프레시 토큰 jti 로 단건 조회. */
    RefreshTokenVo getRefreshTokenByJti(String jti);

    /** 기존 jti 폐기 + 동일 family 의 새 리프레시 토큰 발급. */
    String rotateRefreshToken(LoginVo account, String oldJti, String familyId);

    /** family 단위 일괄 폐기 — reuse 감지 시 호출. */
    void revokeFamily(String loginId, String familyId);

    /** 사용자의 모든 리프레시 토큰 삭제 — sign-out 시 호출. */
    void deleteAllRefreshTokens(String loginId);

    /** 마지막 로그인 일시 갱신. */
    void recordLastLogin(Long accountSn);
}
