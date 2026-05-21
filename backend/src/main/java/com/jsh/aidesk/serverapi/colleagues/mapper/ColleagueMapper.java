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
}
