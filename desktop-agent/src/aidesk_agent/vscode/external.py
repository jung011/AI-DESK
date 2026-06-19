"""외부 VSCode 윈도우 띄우기 — PATH 의 `code` 또는 VSCode.app 번들 안 바이너리.

2026-06-19 비활성 — AI 카드의 VSCode 열기 당분간 사용 안 함.
부활 시 아래 본문 + vscode/__init__.py 의 re-export + server.py 의 import / handler / route 다 같이 해제.
"""
# from __future__ import annotations
#
# import logging
# import shutil
# import subprocess
# from pathlib import Path
#
# log = logging.getLogger(__name__)
#
#
# def _locate_vscode_bundled() -> str | None:
#     """`code` CLI 가 PATH 에 없을 때 VSCode.app 번들 안의 code 바이너리를 찾는다."""
#     try:
#         out = subprocess.run(
#             ["mdfind", "kMDItemCFBundleIdentifier == 'com.microsoft.VSCode'"],
#             capture_output=True,
#             text=True,
#             timeout=3,
#         )
#     except (subprocess.TimeoutExpired, OSError):
#         return None
#     if out.returncode != 0:
#         return None
#     for line in out.stdout.splitlines():
#         candidate = Path(line.strip()) / "Contents" / "Resources" / "app" / "bin" / "code"
#         if candidate.is_file():
#             return str(candidate)
#     return None
#
#
# def open_vscode(workspace_dir: str) -> tuple[int, str]:
#     """Return (rc, message). rc: 0=ok, 2=invalid workspace, 4=not found."""
#     if not workspace_dir or not Path(workspace_dir).is_dir():
#         return 2, "workspaceDir 가 비어있거나 존재하지 않습니다."
#
#     # 1) PATH 의 code
#     code_bin = shutil.which("code")
#     if code_bin:
#         try:
#             subprocess.Popen([code_bin, workspace_dir])
#             log.info("open_vscode (PATH): dir=%s", workspace_dir)
#             return 0, "ok"
#         except OSError:
#             pass
#
#     # 2) VSCode.app 번들 안의 code 바이너리
#     bundled = _locate_vscode_bundled()
#     if bundled:
#         try:
#             subprocess.Popen([bundled, workspace_dir])
#             log.info("open_vscode (bundled): dir=%s via %s", workspace_dir, bundled)
#             return 0, "ok"
#         except OSError as e:
#             log.warning("open_vscode bundled failed: %s", e)
#
#     return 4, (
#         "VSCode 를 찾지 못했습니다. /Applications/Visual Studio Code.app 에 설치되어 있는지, "
#         "또는 VSCode 명령 팔레트에서 'Shell Command: Install code command in PATH' 를 실행했는지 확인하세요."
#     )
