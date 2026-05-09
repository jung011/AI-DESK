package com.jsh.aidesk.serverapi.agents.vo;

import java.util.List;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class AgentListRsVo {

    private List<AgentItemRsVo> list;
    private AgentSummaryRsVo summary;
}
