package com.jsh.aidesk.serverapi.messages.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class AgentUnreadRsVo {

    private String agentId;
    private String agentName;
    private int unread;
}
