package com.jsh.aidesk.serverapi.colleagues.service;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;

import org.springframework.stereotype.Service;

import com.jsh.aidesk.serverapi.colleagues.mapper.ColleagueMapper;
import com.jsh.aidesk.serverapi.colleagues.vo.ColleagueListRsVo;
import com.jsh.aidesk.serverapi.colleagues.vo.ColleagueRsVo;
import com.jsh.aidesk.serverapi.common.jwt.AuthContext;

import lombok.RequiredArgsConstructor;

/**
 * 사내 동료 디렉토리 — 같은 backend 에 가입한 다른 user 의 (me) AI 노출.
 * 케플릭스 control-plane 의존 제거 (자체 채널 모델).
 */
@Service
@RequiredArgsConstructor
public class ColleagueService {

    /** (me) AI updated_at 이 이 시간 이내면 online. */
    private static final Duration ONLINE_WINDOW = Duration.ofMinutes(5);

    private final ColleagueMapper mapper;

    public ColleagueListRsVo getList() {
        Long me = AuthContext.currentAccountSn();
        List<ColleagueRsVo> rows = mapper.selectColleagues(me);
        OffsetDateTime now = OffsetDateTime.now();
        for (ColleagueRsVo r : rows) {
            r.setOnline(isOnline(r.getMeUpdatedAt(), now));
        }
        ColleagueListRsVo rs = new ColleagueListRsVo();
        rs.setList(rows);
        return rs;
    }

    private static boolean isOnline(OffsetDateTime updatedAt, OffsetDateTime now) {
        if (updatedAt == null) return false;
        return Duration.between(updatedAt, now).compareTo(ONLINE_WINDOW) <= 0;
    }
}
