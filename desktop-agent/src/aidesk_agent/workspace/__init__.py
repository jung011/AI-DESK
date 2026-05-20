"""워크스페이스 관련 호스트 조작.

- browse: 폴더/파일 선택 다이얼로그 (osascript choose folder/file)
- scope: (me) 지정 시 kaflix-* MCP scope 이동 + 워크스페이스 자족 .mcp.json
- cleanup: 에이전트 삭제 시 tmux 세션 + Terminal 윈도우 정리 + 옛 대화 jsonl 제거
"""
from .browse import browse_file, browse_workspace
from .cleanup import cleanup_agent
from .scope import scope_workspace

__all__ = [
    "browse_file",
    "browse_workspace",
    "cleanup_agent",
    "scope_workspace",
]
