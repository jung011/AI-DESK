package com.jsh.aidesk.serverapi.agents.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class AgentSummaryRsVo {

    private int total;
    private int active;
    private int waiting;
    private int idle;
    private int done;
    private int error;
}
