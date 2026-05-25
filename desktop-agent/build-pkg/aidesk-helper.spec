# PyInstaller spec for aidesk-helper
# 빌드: build-pkg/build.sh 에서 호출. 직접 호출 시:
#   uv run pyinstaller build-pkg/aidesk-helper.spec --distpath build-pkg/build/pyi-dist
#
# aidesk_agent 패키지가 동적으로 import 하는 모듈들이 있을 수 있어
# collect_submodules 로 통째로 끌어온다.

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hidden = collect_submodules('aidesk_agent')

a = Analysis(
    ['entry.py'],
    pathex=['../src'],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir 빌드 — onefile 의 _MEI 임시 폴더 cleanup 경합 위험 회피.
# onefile (옛) 은 실행 시점에 임시 폴더에 dep 풀고 cleanup. self-kill 반복 시 cleanup 경합으로
# libpython3.11.dylib 등이 사라지는 사고 발생 (우드 mac 사례). onedir 는 모든 dep 가 영구
# 위치 (.pkg 안의 폴더) 에 있어 self-kill 반복에 안전.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='aidesk-helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='aidesk-helper',
)
