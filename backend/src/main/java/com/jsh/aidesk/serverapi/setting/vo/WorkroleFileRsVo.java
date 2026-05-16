package com.jsh.aidesk.serverapi.setting.vo;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class WorkroleFileRsVo {
    /** 신규 AI 부트스트랩 시 읽힐 작업 규칙 문서 파일의 절대 경로. 미설정이면 빈 문자열. */
    private String path;
}
