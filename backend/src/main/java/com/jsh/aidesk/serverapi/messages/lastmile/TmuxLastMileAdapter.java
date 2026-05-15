package com.jsh.aidesk.serverapi.messages.lastmile;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;
import com.jsh.aidesk.serverapi.messages.vo.MessageVo;

import lombok.extern.slf4j.Slf4j;

/**
 * 실제 tmux 세션의 입력창에 send-keys 로 메시지를 주입하는 last mile 어댑터.
 *
 * 1) 수신 AI 의 tmux_session 컬럼을 검사해 has-session 으로 사전 검사
 * 2) 미존재 → onFailed("수신 AI 세션 없음")
 * 3) 존재 → send-keys 로 한 줄 헤더 메시지 주입 + Enter
 *
 * 메시지 헤더 형식 (한 줄, adesk_cli.md 와 정합):
 *   [aidesk · FROM:{fromName} | MSG:{messageId}] {content}  ↳ 응답: adesk reply {messageId} '<답변>'
 *
 * 호출 자체는 동기. 비동기는 MessageService 의 Virtual Thread 가 담당.
 */
@Component
@ConditionalOnProperty(name = "aidesk.tmux.lastmile.enabled", havingValue = "true", matchIfMissing = false)
@Slf4j
public class TmuxLastMileAdapter implements LastMileAdapter {

    private static final long PROCESS_TIMEOUT_SECONDS = 5;

    @Override
    public void deliver(MessageVo message, AgentVo from, AgentVo to, DeliveryCallback callback) {
        String session = to.getTmuxSession();
        if (session == null || session.isBlank()) {
            callback.onFailed("수신 AI 세션 없음 (tmux_session 미설정)");
            return;
        }

        if (!hasSession(session)) {
            callback.onFailed("수신 AI 세션 없음");
            return;
        }

        String rendered = render(message, from);
        if (sendKeys(session, rendered)) {
            callback.onDelivered();
        } else {
            callback.onFailed("tmux send-keys 실패");
        }
    }

    private boolean hasSession(String session) {
        try {
            Process p = new ProcessBuilder("tmux", "has-session", "-t", session)
                    .redirectErrorStream(true)
                    .start();
            boolean finished = p.waitFor(PROCESS_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            return finished && p.exitValue() == 0;
        } catch (Exception e) {
            log.warn("tmux has-session 실패: {}", e.getMessage());
            return false;
        }
    }

    private boolean sendKeys(String session, String text) {
        try {
            // Claude TUI 는 한 번의 send-keys 안에 "텍스트 + Enter" 가 함께 들어오면
            // bracketed-paste 로 인식해 Enter 를 줄바꿈으로 흡수한다. 분리해 보내야 submit.
            //   1) -l (literal) 로 텍스트만 입력
            //   2) 짧은 지연 후 별도 send-keys 로 Enter 키 이벤트 발사
            Process p1 = new ProcessBuilder("tmux", "send-keys", "-l", "-t", session, text)
                    .redirectErrorStream(true)
                    .start();
            boolean f1 = p1.waitFor(PROCESS_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            if (!f1 || p1.exitValue() != 0) return false;

            Thread.sleep(200);

            Process p2 = new ProcessBuilder("tmux", "send-keys", "-t", session, "Enter")
                    .redirectErrorStream(true)
                    .start();
            boolean f2 = p2.waitFor(PROCESS_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            return f2 && p2.exitValue() == 0;
        } catch (Exception e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("tmux send-keys 실패: {}", e.getMessage());
            return false;
        }
    }

    private String render(MessageVo msg, AgentVo from) {
        return String.format(
                "[aidesk · FROM:%s | MSG:%s] %s  ↳ 응답: adesk reply %s '<답변>'",
                from.getAgentName(),
                msg.getMessageId(),
                msg.getContent(),
                msg.getMessageId()
        );
    }
}
