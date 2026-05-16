package com.jsh.aidesk.serverapi.logs.vo;

import lombok.Getter;
import lombok.Setter;

/**
 * 통합 로그 피드의 한 행 — message 또는 action 둘 다 동일 시간순으로 섞임.
 *
 * type=message: agentName/toAgentName/content/category 채워짐
 * type=action : agentName/tool/target/summary/category 채워짐
 */
@Getter
@Setter
public class LogFeedItemRsVo {
    /** "message" | "action" */
    private String type;
    /** 정렬 기준 — ISO-8601 UTC */
    private String createdAt;
    /** code | schema | file | command | discussion */
    private String category;

    /** 발신/수행 주체 */
    private String agentId;
    private String agentName;

    // message 전용
    private String messageId;
    private String toAgentId;
    private String toAgentName;
    private String content;
    /** sent / delivered / replied / failed — pre-flight 실패로 failed 인 경우 errorReason 와 함께 표시. */
    private String messageStatus;
    private String errorReason;

    // action 전용
    private String logId;
    private String tool;
    private String target;
    private String summary;
    private String sessionId;
}
