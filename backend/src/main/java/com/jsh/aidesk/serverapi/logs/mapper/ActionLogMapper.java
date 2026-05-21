package com.jsh.aidesk.serverapi.logs.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.jsh.aidesk.serverapi.logs.vo.ActionLogVo;

@Mapper
public interface ActionLogMapper {

    int insert(ActionLogVo entity);

    /** 카테고리/기간 필터 + 최신 N 개. 본인 user 의 agent 가 수행한 액션만. category=null 이면 전체. */
    List<ActionLogVo> selectFeed(
            @Param("ownerAccountSn") Long ownerAccountSn,
            @Param("category") String category,
            @Param("limit") int limit
    );
}
