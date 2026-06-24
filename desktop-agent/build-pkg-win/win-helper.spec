# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — win-helper (Windows AI Desk helper, onefile)
#
# 빌드:
#   cd desktop-agent
#   uv run pyinstaller build-pkg-win/win-helper.spec --noconfirm
#
# 산출물: desktop-agent/dist/win-helper.exe (단일 실행파일)
# 주의: node 스크립트(adesk-cli/bin, aidesk-channel)는 exe 에 *번들하지 않고* installer 가
#       exe 옆에 동봉한다. win_helper._resource_base() 가 sys.executable 옆에서 찾기 때문.
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

DA = os.path.dirname(SPECPATH)  # desktop-agent/

# pywinpty(winpty) 는 네이티브 .dll/.pyd 동반 → collect_all 로 통째 수집.
wp_datas, wp_bins, wp_hidden = collect_all("winpty")
hidden = wp_hidden + collect_submodules("aiohttp") + ["httpx", "httpx_sse"]

a = Analysis(
    [os.path.join(DA, "win_helper.py")],
    pathex=[],
    binaries=wp_bins,
    datas=wp_datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="win-helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # 백그라운드 서비스 — 콘솔창 없이 (HKCU Run 자동시작 시 창 안 뜸). 로그는 win-helper.log
)
