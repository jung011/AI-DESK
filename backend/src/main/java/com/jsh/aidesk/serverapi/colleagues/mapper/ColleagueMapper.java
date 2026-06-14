package com.jsh.aidesk.serverapi.colleagues.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.jsh.aidesk.serverapi.colleagues.vo.ColleagueRsVo;

@Mapper
public interface ColleagueMapper {

    /**
     * 사내 동료 list — 본인 user 외 모든 t_user + 그들의 (me) AI 정보.
     * (me) AI 가 없는 user 도 row 반환 (meAgentId=null).
     */
    List<ColleagueRsVo> selectColleagues(@Param("excludeAccountSn") Long excludeAccountSn);

    /**
     * 본인 user 의 외부 AI list — agent_type='external' row 만. 사내 동료 응답에 합쳐 노출.
     * frontend 가 type='external' 로 카드 구분.
     */
    List<ColleagueRsVo> selectMyExternalAgents(@Param("ownerAccountSn") Long ownerAccountSn);
}
