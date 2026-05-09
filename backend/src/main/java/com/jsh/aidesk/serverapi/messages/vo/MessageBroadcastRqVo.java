package com.jsh.aidesk.serverapi.messages.vo;

import java.util.List;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

/**
 * 멀티캐스트 발신 요청. 한 번에 여러 수신자에게 같은 본문을 fan-out 한다.
 *
 * 답장 체인은 multicast 의도와 어색하게 결합되므로 본 요청에선 지원하지 않는다.
 */
@Getter
@Setter
@ToString
public class MessageBroadcastRqVo {

    @NotBlank
    @Size(max = 36)
    private String fromAgentId;

    @NotEmpty
    @Size(min = 1, max = 50)
    private List<@NotBlank @Size(max = 36) String> toAgentIds;

    @NotBlank
    @Size(max = 1000)
    private String content;
}
