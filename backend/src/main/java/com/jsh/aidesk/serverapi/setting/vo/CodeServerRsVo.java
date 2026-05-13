package com.jsh.aidesk.serverapi.setting.vo;

import lombok.AllArgsConstructor;
import lombok.Getter;

/** 프론트가 임베드용 iframe URL 을 만들고 헬스 표시를 결정할 수 있도록 제공. */
@Getter
@AllArgsConstructor
public class CodeServerRsVo {
    /** 예: http://localhost:30082 — application.yaml `vscode.code-server-url`. */
    private String url;
    /** 백엔드가 HEAD 요청으로 확인한 reachability. false 면 프론트는 "미기동" 안내. */
    private boolean alive;
}
