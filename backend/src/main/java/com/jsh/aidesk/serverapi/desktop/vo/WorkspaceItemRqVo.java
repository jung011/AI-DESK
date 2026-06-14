package com.jsh.aidesk.serverapi.desktop.vo;

import lombok.Getter;
import lombok.Setter;

/**
 * Desktop Agent 가 보고하는 워크스페이스 단위 정보.
 *
 * Helper 는 `~/.claude/projects/{escaped}/` 디렉토리를 스캔해 최신 jsonl 의 mtime
 * 으로 status 를 추정하고, 가능하면 jsonl 안의 cwd 를 추출해 workspaceDir 도 함께 보낸다.
 */
@Getter
@Setter
public class WorkspaceItemRqVo {

    /** `~/.claude/projects/` 의 디렉토리명 (영숫자/언더스코어 외는 '-'). */
    private String encodedDir;

    /** jsonl 안에서 추출한 실제 cwd. null 일 수 있음 (jsonl 에 cwd 라인이 없거나 못 읽었을 때). */
    private String workspaceDir;

    private String latestJsonl;
    private String latestMtime;
    private Long ageSec;

    /** "active" / "idle" / "done" / "unknown" — 백엔드 AgentStatusWatcher 와 동일한 임계값으로 추정. */
    private String status;
}
