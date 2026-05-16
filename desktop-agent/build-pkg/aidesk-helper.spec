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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='aidesk-helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
