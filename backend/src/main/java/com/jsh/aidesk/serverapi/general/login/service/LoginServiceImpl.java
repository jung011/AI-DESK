package com.jsh.aidesk.serverapi.general.login.service;

import com.jsh.aidesk.serverapi.agents.mapper.AgentMapper;
import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.common.jwt.JwtProvider;
import com.jsh.aidesk.serverapi.common.util.HashUtil;
import com.jsh.aidesk.serverapi.general.login.mapper.LoginMapper;
import com.jsh.aidesk.serverapi.general.login.vo.LoginVo;
import com.jsh.aidesk.serverapi.general.login.vo.RefreshTokenVo;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class LoginServiceImpl implements LoginService {

    private final LoginMapper loginMapper;
    private final AgentMapper agentMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtProvider jwtProvider;

    @Override
    @Transactional(readOnly = true)
    public LoginVo authenticate(LoginVo vo) {
        LoginVo account = loginMapper.selectAccountByLoginId(vo.getLoginId());
        if (account == null) return null;
        if (!passwordEncoder.matches(vo.getPassword(), account.getPassword())) return null;
        return account;
    }

    @Override
    @Transactional(readOnly = true)
    public LoginVo getActiveAccountBySn(Long accountSn) {
        return loginMapper.selectAccountByAccountSn(accountSn);
    }

    @Override
    @Transactional
    public LoginVo signup(String loginId, String rawPassword) {
        String normalized = loginId.trim().toLowerCase();
        if (loginMapper.existsByLoginId(normalized) > 0) {
            return null;
        }
        LoginVo vo = new LoginVo();
        vo.setLoginId(normalized);
        vo.setPassword(passwordEncoder.encode(rawPassword));
        vo.setDisplayName(normalized);   // 회원가입 시 displayName = loginId (사용자 결정)
        vo.setRole("USER");
        loginMapper.insertAccount(vo);   // useGeneratedKeys 로 accountSn 채워짐

        // 휴먼 entity — 채팅에서 user 본인이 보낸 메시지의 발신자로 쓰임. user 별 1 row.
        // model='human' + tmux_session='__human__:<sn>'. helper/last-mile 은 이 패턴을 만나면
        // tmux send-keys skip + 즉시 delivered 마킹.
        AgentVo human = new AgentVo();
        human.setAgentId(UUID.randomUUID().toString());
        human.setOwnerAccountSn(vo.getAccountSn());
        human.setAgentName("휴먼");
        human.setWorkspaceDir("");
        human.setTmuxSession("__human__:" + vo.getAccountSn());
        human.setStatus("active");
        human.setModel("human");
        agentMapper.insert(human);

        // generated 시각 컬럼 (created_at) 은 select 로 재조회해 채워 반환
        return loginMapper.selectAccountByAccountSn(vo.getAccountSn());
    }

    @Override
    @Transactional
    public void recordLastLogin(Long accountSn) {
        loginMapper.updateLastLoginDt(accountSn);
    }

    @Override
    @Transactional
    public String issueNewRefreshToken(LoginVo account) {
        String familyId = UUID.randomUUID().toString();
        return issueRefreshToken(account, familyId);
    }

    @Override
    @Transactional(readOnly = true)
    public RefreshTokenVo getRefreshTokenByJti(String jti) {
        return loginMapper.selectRefreshTokenByJti(jti);
    }

    @Override
    @Transactional
    public String rotateRefreshToken(LoginVo account, String oldJti, String familyId) {
        loginMapper.revokeRefreshTokenByJti(oldJti);
        return issueRefreshToken(account, familyId);
    }

    @Override
    @Transactional
    public void revokeFamily(String loginId, String familyId) {
        loginMapper.revokeRefreshTokenFamily(loginId, familyId);
    }

    @Override
    @Transactional
    public void deleteAllRefreshTokens(String loginId) {
        loginMapper.deleteRefreshTokenByLoginId(loginId);
    }

    private String issueRefreshToken(LoginVo account, String familyId) {
        String jti = UUID.randomUUID().toString();
        String token = jwtProvider.createRefreshToken(account.getLoginId(), jti);

        RefreshTokenVo vo = new RefreshTokenVo();
        vo.setJti(jti);
        vo.setAccountSn(account.getAccountSn());
        vo.setLoginId(account.getLoginId());
        vo.setFamilyId(familyId);
        vo.setTokenHash(HashUtil.sha256(token));
        vo.setExpiresAt(OffsetDateTime.now().plusSeconds(jwtProvider.getRefreshExpirationSeconds()));
        loginMapper.insertRefreshToken(vo);

        return token;
    }
}
