package com.jsh.aidesk.serverapi.messages.policy;

import org.springframework.stereotype.Component;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

import lombok.RequiredArgsConstructor;

/**
 * messages_backend.md 의 정책 모듈.
 *
 * - hop limit       : 답장 체인 깊이 ≤ 10
 * - rate limit      : 발신 AI 분당 30건 이하
 * - context guard   : 수신 AI contextPct ≥ 90 → 거절
 * - status guard    : 수신 AI status = done → 거절
 * - self-message    : from == to → 거절 (Service 에서 별도 400 처리)
 */
@Component
@RequiredArgsConstructor
public class MessagePolicyChecker {

    private static final int RATE_LIMIT_PER_MINUTE = 30;
    private static final int HOP_LIMIT = 10;
    private static final int CONTEXT_LIMIT = 90;

    private final MessageMapper messageMapper;

    public PolicyResult check(AgentVo from, AgentVo to, MessageVo parent) {
        if ("done".equals(to.getStatus())) {
            return PolicyResult.reject("완료 상태 AI는 수신 불가");
        }
        if (to.getContextPct() != null && to.getContextPct() >= CONTEXT_LIMIT) {
            return PolicyResult.reject("수신 AI 컨텍스트 " + CONTEXT_LIMIT + "% 초과");
        }
        if (parent != null) {
            int parentHop = parent.getHopCount() == null ? 0 : parent.getHopCount();
            if (parentHop + 1 > HOP_LIMIT) {
                return PolicyResult.reject("위임 깊이 초과 (max " + HOP_LIMIT + ")");
            }
        }
        int recent = messageMapper.countRecentByFrom(from.getAgentId(), 60);
        if (recent >= RATE_LIMIT_PER_MINUTE) {
            return PolicyResult.reject("발신 한도 초과 (분당 " + RATE_LIMIT_PER_MINUTE + "건)");
        }
        return PolicyResult.accept();
    }
}
