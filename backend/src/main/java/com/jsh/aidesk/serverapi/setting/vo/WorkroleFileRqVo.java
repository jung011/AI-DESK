package com.jsh.aidesk.serverapi.setting.vo;

import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class WorkroleFileRqVo {
    /** 빈 문자열 허용 — "주입 안 함" 의미. */
    @Size(max = 500)
    private String path;
}
