#!/bin/bash
# AI Desk Helper macOS .pkg 빌드 스크립트.
#
# 사용:
#   ./build-pkg/build.sh                # 버전 0.1.0 으로 빌드
#   VERSION=0.2.0 ./build-pkg/build.sh  # 명시적 버전
#
# 산출물: build-pkg/dist/AIDeskHelper-${VERSION}-${ARCH}.pkg
#
# 흐름:
#   1) PyInstaller 로 단일 바이너리 생성
#   2) payload 디렉토리 (= 설치 후 / 루트) 구성
#   3) pkgbuild 로 component pkg 생성
#   4) productbuild 로 마법사 UI 가 붙은 distribution pkg 생성

set -euo pipefail

VERSION="${VERSION:-0.1.0}"
ARCH="$(uname -m)"
PKG_ID="com.kaflix.aidesk-helper"

ROOT="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_AGENT="$(cd "$ROOT/.." && pwd)"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
PAYLOAD="$BUILD/payload"

echo "→ Cleaning build/ dist/"
rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD" "$DIST"

echo "→ [1/4] Running PyInstaller"
cd "$DESKTOP_AGENT"
uv run pyinstaller \
    --clean --noconfirm \
    --distpath "$BUILD/pyi-dist" \
    --workpath "$BUILD/pyi-work" \
    "$ROOT/aidesk-helper.spec"

BINARY="$BUILD/pyi-dist/aidesk-helper"
[[ -x "$BINARY" ]] || { echo "✗ PyInstaller binary not found: $BINARY"; exit 1; }

echo "→ [2/4] Composing payload"
mkdir -p "$PAYLOAD/usr/local/bin"
mkdir -p "$PAYLOAD/usr/local/share/aidesk/hooks"

cp "$BINARY" "$PAYLOAD/usr/local/bin/aidesk-helper"
chmod 755 "$PAYLOAD/usr/local/bin/aidesk-helper"

cp "$DESKTOP_AGENT/scripts/aidesk-action-hook.cjs" "$PAYLOAD/usr/local/share/aidesk/hooks/"
cp "$DESKTOP_AGENT/scripts/aidesk-prompt-hook.cjs" "$PAYLOAD/usr/local/share/aidesk/hooks/"

# statusline 은 adesk-cli/bin 에 있는 별도 패키지 — monorepo 형제 디렉토리에서 복사
STATUSLINE_SRC="$(cd "$DESKTOP_AGENT/.." && pwd)/adesk-cli/bin/aidesk-statusline.cjs"
if [[ -f "$STATUSLINE_SRC" ]]; then
    cp "$STATUSLINE_SRC" "$PAYLOAD/usr/local/share/aidesk/hooks/"
else
    echo "⚠ statusline 스크립트 없음 — 건너뜀: $STATUSLINE_SRC"
fi

chmod 755 "$PAYLOAD/usr/local/share/aidesk/hooks/"*.cjs

# 설치 스크립트 실행 권한 보정
chmod 755 "$ROOT/scripts/preinstall" "$ROOT/scripts/postinstall"

echo "→ [3/4] pkgbuild (component)"
pkgbuild \
    --root "$PAYLOAD" \
    --scripts "$ROOT/scripts" \
    --identifier "$PKG_ID" \
    --version "$VERSION" \
    --install-location / \
    "$BUILD/AIDeskHelper-component.pkg"

echo "→ [4/4] productbuild (distribution)"
OUT="$DIST/AIDeskHelper-${VERSION}-${ARCH}.pkg"
productbuild \
    --distribution "$ROOT/distribution.xml" \
    --package-path "$BUILD" \
    --resources "$ROOT/resources" \
    "$OUT"

echo ""
echo "✓ Built: $OUT"
echo ""
echo "설치 (테스터):"
echo "  sudo installer -pkg \"$OUT\" -target /"
echo "  또는 Finder 에서 우클릭 → 열기 (미서명 경고 우회)"
echo ""
echo "확인:"
echo "  launchctl list | grep com.aidesk.agent"
echo "  tail -f ~/Library/Logs/aidesk-agent.err"
