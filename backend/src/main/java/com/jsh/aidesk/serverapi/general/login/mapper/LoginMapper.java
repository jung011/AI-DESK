package com.jsh.aidesk.serverapi.general.login.mapper;

import com.jsh.aidesk.serverapi.general.login.vo.LoginVo;
import com.jsh.aidesk.serverapi.general.login.vo.RefreshTokenVo;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface LoginMapper {

    /** 로그인 ID 로 계정 조회. */
    LoginVo selectAccountByLoginId(@Param("loginId") String loginId);

    /** account_sn 으로 계정 조회 — refresh / me 흐름에서 사용. */
    LoginVo selectAccountByAccountSn(@Param("accountSn") Long accountSn);

    /** loginId 존재 여부 (signup 중복 검사). */
    int existsByLoginId(@Param("loginId") String loginId);

    /** 마지막 로그인 일시 갱신. */
    int updateLastLoginDt(@Param("accountSn") Long accountSn);

    /** 신규 사용자 insert. 성공 시 vo.accountSn 에 generated key 세팅. */
    int insertAccount(LoginVo vo);

    int insertRefreshToken(RefreshTokenVo vo);

    RefreshTokenVo selectRefreshTokenByJti(@Param("jti") String jti);

    int revokeRefreshTokenByJti(@Param("jti") String jti);

    int revokeRefreshTokenFamily(@Param("loginId") String loginId, @Param("familyId") String familyId);

    int deleteRefreshTokenByLoginId(@Param("loginId") String loginId);
}
