package com.jsh.aidesk.serverapi.usage.vo;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class LocalUsageRsVo {
    /** 0~100. JSONL 을 못 찾으면 0. */
    private int pct;
    /** 분자 (input + cache_read + cache_creation). */
    private long tokens;
    /** 분모 (현재는 1,000,000 고정). */
    private long window;
    /** 어느 JSONL 을 참조했는지 (디버그/투명성용 — 빈 문자열이면 데이터 없음). */
    private String source;
}
