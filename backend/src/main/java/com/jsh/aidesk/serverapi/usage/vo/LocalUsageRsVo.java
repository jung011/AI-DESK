package com.jsh.aidesk.serverapi.usage.vo;

import lombok.Getter;
import lombok.Setter;

/**
 * 로컬 Claude Code 사용량 응답.
 *
 * 값들은 statusline 스크립트(adesk-cli/bin/aidesk-statusline.js)가 ~/.claude/aidesk-usage/
 * 디렉토리에 매 프롬프트마다 기록한 상태에서 읽어온다 — 즉 /usage 와 동일 소스.
 * 스크립트가 등록되지 않은 환경에서는 모든 값이 null/-1 로 내려간다.
 */
@Getter
@Setter
public class LocalUsageRsVo {
    /** 5시간 롤링 rate-limit 사용률 (0~100). 데이터 없으면 -1. */
    private int fiveHourPct = -1;
    /** 5시간 윈도우 리셋 시각 — Unix epoch seconds. 없으면 0. */
    private long fiveHourResetsAt = 0;

    /** 주간 토큰 사용률 (0~100). 없으면 -1. */
    private int weeklyPct = -1;
    /** 주간 윈도우 리셋 시각. 없으면 0. */
    private long weeklyResetsAt = 0;

    /** 컨텍스트 사용률 (0~100). 데이터 없으면 -1. */
    private int contextPct = -1;

    /** 어떤 세션 파일에서 읽었는지 (디버그용 — 빈 문자열이면 데이터 없음). */
    private String source = "";

    /** statusline 이 등록되어 있는지. false 면 프론트에서 안내 배너 표시. */
    private boolean ready = false;
}
