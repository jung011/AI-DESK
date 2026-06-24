# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AIDeskHelper-Setup.exe (Windows 자체추출 설치기, onefile, windowed)
#
# 빌드(build.ps1 이 자동 수행):
#   1) win-helper.exe 빌드 → 스테이징 → build-win/payload.zip 생성
#   2) cd desktop-agent && uv run pyinstaller build-pkg-win/win-installer.spec --noconfirm
#
# payload.zip(루트에 win-helper.exe / adesk-cli / aidesk-channel)을 datas 로 동봉.
# installer.py 가 런타임에 %LOCALAPPDATA%\AIDeskHelper 로 추출 + 자동시작 등록.
import os

DA = os.path.dirname(SPECPATH)  # desktop-agent/
PAYLOAD = os.path.join(DA, "build-win", "payload.zip")
if not os.path.isfile(PAYLOAD):
    raise SystemExit(f"payload.zip 없음: {PAYLOAD} — build.ps1 이 먼저 생성해야 함")

a = Analysis(
    [os.path.join(DA, "build-pkg-win", "installer.py")],
    pathex=[],
    binaries=[],
    datas=[(PAYLOAD, ".")],  # _MEIPASS 루트에 payload.zip
    hiddenimports=[],
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
    name="AIDeskHelper-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # windowed — 진행/결과는 MessageBox
)
