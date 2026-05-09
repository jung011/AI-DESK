package com.jsh.aidesk.serverapi.messages.vo;

import java.util.List;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

/**
 * 멀티캐스트 결과 — fan-out 한 메시지 목록 + 집계.
 *
 *   totalAttempted = 실제 INSERT 시도 (자기 자신 제외 + distinct + 존재하는 수신자)
 *   succeeded      = status != failed 인 메시지 수
 *   failed         = status = failed 인 메시지 수
 *   notFound       = toAgentIds 중 미존재(또는 자기자신/중복) 라 스킵된 수
 */
@Getter
@Setter
@ToString
public class MessageBroadcastRsVo {

    private List<MessageItemRsVo> list;
    private int totalAttempted;
    private int succeeded;
    private int failed;
    private int notFound;
}
