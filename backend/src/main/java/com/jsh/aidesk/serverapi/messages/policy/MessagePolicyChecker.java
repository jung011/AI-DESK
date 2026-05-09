package com.jsh.aidesk.serverapi.messages.policy;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.mapper.MessageMapper;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * messages_backend.md 의 정책 모듈.
 *
 * - hop limit       : 답장 체인 깊이 ≤ messages.policy.hop-limit
 * - rate limit      : 발신 AI 분당 messages.policy.rate-limit-per-minute 건 이하
 * - context guard   : 수신 AI contextPct ≥ messages.policy.context-limit-pct → 거절
 * - status guard    : 수신 AI status = done → 거절
 * - self-message    : from == to → 거절 (Service 에서 별도 400 처리)
 *
 * 임계값은 application.yaml 의 messages.policy.* 로 외부화. 운영 시 yaml 만 고쳐 재기동해도 반영.
 * 거절 시 INFO 레벨 로그 — 감사·모니터링 용.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class MessagePolicyChecker {

    @Value("${messages.policy.rate-limit-per-minute:30}")
    private int rateLimitPerMinute;

    @Value("${messages.policy.hop-limit:10}")
    private int hopLimit;

    @Value("${messages.policy.context-limit-pct:90}")
    private int contextLimitPct;

    private final MessageMapper messageMapper;

    public PolicyResult check(AgentVo from, AgentVo to, MessageVo parent) {
        PolicyResult result = doCheck(from, to, parent);
        if (!result.accepted()) {
            log.info("policy reject: from='{}' to='{}' reason='{}'",
                    from.getAgentName(), to.getAgentName(), result.errorReason());
        }
        return result;
    }

    private PolicyResult doCheck(AgentVo from, AgentVo to, MessageVo parent) {
        if ("done".equals(to.getStatus())) {
            return PolicyResult.reject("완료 상태 AI는 수신 불가");
        }
        if (to.getContextPct() != null && to.getContextPct() >= contextLimitPct) {
            return PolicyResult.reject("수신 AI 컨텍스트 " + contextLimitPct + "% 초과");
        }
        if (parent != null) {
            int parentHop = parent.getHopCount() == null ? 0 : parent.getHopCount();
            if (parentHop + 1 > hopLimit) {
                return PolicyResult.reject("위임 깊이 초과 (max " + hopLimit + ")");
            }
        }
        int recent = messageMapper.countRecentByFrom(from.getAgentId(), 60);
        if (recent >= rateLimitPerMinute) {
            return PolicyResult.reject("발신 한도 초과 (분당 " + rateLimitPerMinute + "건)");
        }
        return PolicyResult.accept();
    }
}
