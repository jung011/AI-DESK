package com.jsh.aidesk.serverapi.messages.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class MessageCreateRqVo {

    @NotBlank
    @Size(max = 36)
    private String fromAgentId;

    @NotBlank
    @Size(max = 36)
    private String toAgentId;

    @NotBlank
    @Size(max = 1000)
    private String content;

    /** 답장 체인 — 원본 메시지 UUID. 없으면 신규 1차 발신. */
    @Size(max = 36)
    private String replyToMessageId;
}
