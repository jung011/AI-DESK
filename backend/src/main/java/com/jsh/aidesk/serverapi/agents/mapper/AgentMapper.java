package com.jsh.aidesk.serverapi.agents.mapper;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;

@Mapper
public interface AgentMapper {

    List<AgentVo> selectList(@Param("status") String status);

    List<Map<String, Object>> selectStatusCounts();

    AgentVo selectById(@Param("agentId") String agentId);

    int insert(AgentVo agent);

    int softDelete(@Param("agentId") String agentId);

    /**
     * 세션 파일 감지 스케줄러용 — 상태와 컨텍스트 사용률을 함께 갱신.
     * contextPct 가 null 이면 컬럼은 변경하지 않는다 (status 만 변경).
     */
    int updateStatusFromWatcher(@Param("agentId") String agentId,
                                 @Param("status") String status,
                                 @Param("contextPct") Integer contextPct);
}
