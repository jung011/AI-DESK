package com.jsh.aidesk.serverapi.desktop.vo;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class TmuxSessionItemRqVo {
    private String name;
    private Boolean attached;
    private Integer windows;
}
