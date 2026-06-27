"""claude TUI 의 yes/no option dialog detection.

claude code 가 tool 권한 / Plan mode / Bash 위험 등 prompt 띄울 때 화면 footer 위에
`1. Yes` `2. Yes, don't ask again` `3. No` 같은 *번호 + 라벨* option list 박힘.
tmux capture-pane 결과 안 그 dialog 검출 → 채팅 페이지가 dynamic 버튼 표시 → 사용자
응답 시 helper 가 send-keys 박음.

[detection 규칙]
1. footer anchor (`for agents` 또는 `❯`) 마지막 ~8 line 안 박혀있어야 — claude TUI alive
2. footer 위 12 line 안에서 `^\\s*(\\d+)\\.\\s+(.+)` 매칭 line 수집
3. 매칭 indices 가 *1, 2, 3...* sequential 이고 2개 이상 시 dialog 확정
4. 그 외 = None (dialog 없음 또는 알 수 없는 pattern)
"""
from __future__ import annotations

import logging
import re
import subprocess

log = logging.getLogger(__name__)

_OPTION_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
_FOOTER_INDICATORS = ("for agents", "❯")
_FOOTER_SEARCH_DEPTH = 8  # 마지막 N line 안에서 footer anchor 찾기
_OPTION_SEARCH_DEPTH = 12  # footer 위 N line 안에서 option list 찾기
_MIN_OPTIONS = 2


def detect_prompt_dialog(tmux_session: str) -> dict | None:
    """주어진 tmux session 의 capture-pane 결과 안 dialog 검출.

    Returns:
        {"options": [{"index": 1, "label": "Yes"}, ...]} or None.
    """
    try:
        cap = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", tmux_session, "-S", "-30"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.SubprocessError, OSError) as e:
        log.debug("prompt-detect: capture-pane failed session=%s err=%s", tmux_session, e)
        return None
    if cap.returncode != 0:
        return None
    return _parse_screen(cap.stdout or "")


def _parse_screen(screen: str) -> dict | None:
    lines = screen.splitlines()
    if not lines:
        return None
    # footer anchor — 마지막 N line 안
    footer_idx: int | None = None
    for i in range(len(lines) - 1, max(-1, len(lines) - 1 - _FOOTER_SEARCH_DEPTH), -1):
        if any(ind in lines[i] for ind in _FOOTER_INDICATORS):
            footer_idx = i
            break
    if footer_idx is None:
        return None
    # footer 위 N line 안 option list pattern
    search_start = max(0, footer_idx - _OPTION_SEARCH_DEPTH)
    options = []
    for ln in lines[search_start:footer_idx]:
        m = _OPTION_LINE_RE.match(ln)
        if m:
            options.append({"index": int(m.group(1)), "label": m.group(2).strip()})
    if len(options) < _MIN_OPTIONS:
        return None
    # sequential 1, 2, 3... 정합 확인
    indices = [o["index"] for o in options]
    if indices != list(range(1, len(indices) + 1)):
        return None
    return {"options": options}
