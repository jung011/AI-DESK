package com.jsh.aidesk.serverapi.colleagues.vo;

import java.time.OffsetDateTime;

import lombok.Data;

/**
 * 사내 동료 단건 — 같은 backend 의 다른 user 의 (me) AI 정보.
 * (me) 미지정 user 는 meAgentId=null 로 반환.
 */
@Data
public class ColleagueRsVo {
    private Long accountSn;
    private String loginId;
    private String displayName;

    private String meAgentId;
    private String meAgentName;
    private String meStatus;
    private Integer meContextPct;
    private String meWorkspaceDir;
    private OffsetDateTime meUpdatedAt;

    /** (me) AI 의 updated_at 이 최근 5분 이내면 true. service 가 계산. */
    private boolean online;

    /** agent 분류 — 'me' (다른 user 의 me 또는 본인 user 의 me) / 'external' (본인 user 의 외부 AI service). frontend 카드 분기. */
    private String agentType;
}
