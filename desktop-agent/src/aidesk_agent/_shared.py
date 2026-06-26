"""sub-package 간 공유되는 작은 헬퍼들 — terminal/vscode/workspace/claude 어느 한 곳에도 묶이지 않는 공통 부분.

큰 함수는 절대 여기 넣지 말 것. 한 sub-package 안에서만 쓰이면 그 안의 private 으로.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_ESCAPE_RE = re.compile(r"[^A-Za-z0-9_]")


def aidesk_share_dir() -> str:
    """helper-pkg payload install root — dev / prod 분기.

    prod (.pkg)  : /usr/local/share/aidesk/
    dev   (.pkg) : /usr/local/share/aidesk-dev/

    build-dev.sh 의 PAYLOAD 가 -dev/ 자리 사용 — helper python 코드가 같은 자리
    참조해야 dev .pkg 검증 시 *prod 파일 안 사용*. 일관성 룰
    [[feedback-dev-prod-environment-separation]] 의 응용.
    """
    return "/usr/local/share/aidesk-dev" if os.environ.get("AIDESK_ENV") == "dev" else "/usr/local/share/aidesk"


def aidesk_hooks_dir() -> Path:
    """Claude Code hooks (action/prompt/compact .cjs + statusline). dev/prod 분기."""
    return Path(aidesk_share_dir()) / "hooks"


def applescript_escape(s: str) -> str:
    """AppleScript 문자열 리터럴 escape — backslash + double quote."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def encoded_project_dir(workspace_dir: str) -> Path:
    """`~/.claude/projects/{escaped}/` 경로 (claude code 의 대화 히스토리 위치).

    워크스페이스 경로의 알파벳/숫자/언더스코어 외 모든 문자를 `-` 로 치환한 폴더명.
    """
    escaped = _ESCAPE_RE.sub("-", workspace_dir)
    return Path.home() / ".claude" / "projects" / escaped


def has_past_session(workspace_dir: str) -> bool:
    """`~/.claude/projects/{escaped}/` 안에 `.jsonl` 이 하나라도 있으면 옛 대화가 있다고 본다.

    `claude -c` (continue) 호출 여부 결정에 사용.
    """
    project_dir = encoded_project_dir(workspace_dir)
    if not project_dir.is_dir():
        return False
    for p in project_dir.rglob("*.jsonl"):
        if p.is_file():
            return True
    return False
