package com.jsh.aidesk.serverapi.messages.vo;

import java.util.List;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class MessageListRsVo {

    private List<MessageItemRsVo> list;
    private boolean hasMore;
}
