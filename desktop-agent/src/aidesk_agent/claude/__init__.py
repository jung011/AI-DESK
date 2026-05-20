"""Claude Code 관련 자동화 — 부트스트랩, 워크스페이스 스캔, hook 등록, statusline.

- bootstrap: 신규 AI 생성 시 settings.local.json + tmux 자동 spawn + prompt inject
- scanner: ~/.claude/projects 워크스페이스 + 마지막 modified time 스캔
- prompt_hook: UserPromptSubmit / Notification / Stop 훅 등록 (응답 대기 감지)
- action_hook: PostToolUse 훅 등록 (mutation 감사 — Write/Edit/Bash/DB MCP)
- usage: statusline 훅 + 로컬 사용량 메트릭
"""
from .bootstrap import bootstrap_agent
from .scanner import scan_workspaces

__all__ = ["bootstrap_agent", "scan_workspaces"]
