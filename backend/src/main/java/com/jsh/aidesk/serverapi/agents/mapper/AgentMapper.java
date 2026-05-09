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
}
