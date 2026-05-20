"""tmux 세션 관리.

- scanner: `tmux list-sessions` 결과를 dataclass 로 반환 (대시보드 + reporter)
- sse_consumer: backend SSE 받아 `tmux send-keys` (메시지 last-mile delivery)
- pty_bridge: 임베드 터미널 xterm.js WebSocket attach (현재 비활성, dashboard 임베드와 짝)
"""
from .scanner import scan_sessions
from .sse_consumer import consumer_loop

__all__ = ["scan_sessions", "consumer_loop"]
