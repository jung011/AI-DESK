"""VSCode 통합.

- external: 시스템에 설치된 VSCode.app 을 외부 윈도우로 띄움 (active)
- code_server: brew code-server 자동 spawn (현재 비활성, dashboard 의 임베드 VSCode 사이드 패널과 짝)
"""
from .external import open_vscode

__all__ = ["open_vscode"]
