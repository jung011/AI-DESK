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

# zellij multiplexer 자동 다운로드 — PyInstaller spec 의 datas=[('../bin/zellij', 'bin')] 가 참조.
# 같은 mac 에서 재빌드 시 cache 활용 (한 번 다운 받으면 재사용).
ZELLIJ_VERSION="${ZELLIJ_VERSION:-0.44.3}"
ZELLIJ_BIN="$DESKTOP_AGENT/bin/zellij"
if [[ "$ARCH" == "arm64" ]]; then
    ZELLIJ_TARGET="aarch64-apple-darwin"
elif [[ "$ARCH" == "x86_64" ]]; then
    ZELLIJ_TARGET="x86_64-apple-darwin"
else
    echo "✗ 지원 안 되는 ARCH=$ARCH (zellij)"; exit 1
fi
if [[ ! -f "$ZELLIJ_BIN" ]] || ! "$ZELLIJ_BIN" --version 2>/dev/null | grep -q "$ZELLIJ_VERSION"; then
    echo "→ [0/4] zellij v${ZELLIJ_VERSION} (${ZELLIJ_TARGET}) 다운로드"
    mkdir -p "$DESKTOP_AGENT/bin"
    curl -fSL --max-time 120 \
        "https://github.com/zellij-org/zellij/releases/download/v${ZELLIJ_VERSION}/zellij-${ZELLIJ_TARGET}.tar.gz" \
        -o "$DESKTOP_AGENT/bin/zellij.tar.gz"
    tar -xzf "$DESKTOP_AGENT/bin/zellij.tar.gz" -C "$DESKTOP_AGENT/bin"
    rm "$DESKTOP_AGENT/bin/zellij.tar.gz"
    chmod +x "$ZELLIJ_BIN"
    # macOS Gatekeeper 대응 — unsigned binary 의 quarantine 회피 + ad-hoc 코드사인.
    # [[feedback-macos-gatekeeper-binary-download]]
    xattr -d com.apple.quarantine "$ZELLIJ_BIN" 2>/dev/null || true
    codesign --force --sign - "$ZELLIJ_BIN" 2>/dev/null || true
fi
echo "  zellij: $("$ZELLIJ_BIN" --version)"

echo "→ [1/4] Running PyInstaller"
cd "$DESKTOP_AGENT"
uv run pyinstaller \
    --clean --noconfirm \
    --distpath "$BUILD/pyi-dist" \
    --workpath "$BUILD/pyi-work" \
    "$ROOT/aidesk-helper.spec"

HELPER_DIR="$BUILD/pyi-dist/aidesk-helper"
[[ -d "$HELPER_DIR" && -x "$HELPER_DIR/aidesk-helper" ]] || { echo "✗ PyInstaller onedir not found: $HELPER_DIR"; exit 1; }

echo "→ [2/4] Composing payload"
mkdir -p "$PAYLOAD/usr/local/bin"
mkdir -p "$PAYLOAD/usr/local/share/aidesk/hooks"
mkdir -p "$PAYLOAD/usr/local/share/aidesk/helper-app"

# onedir 폴더 전체 (binary + _internal/ 의 libpython 등 dep 영구 위치) 복사.
# onefile 의 _MEI 임시 폴더 cleanup 경합 위험 회피.
cp -R "$HELPER_DIR"/. "$PAYLOAD/usr/local/share/aidesk/helper-app/"
chmod 755 "$PAYLOAD/usr/local/share/aidesk/helper-app/aidesk-helper"

# /usr/local/bin/aidesk-helper 는 helper-app 의 binary 로 symlink — LaunchAgent plist 의
# ProgramArguments (/usr/local/bin/aidesk-helper) 와 호환 유지.
ln -sf "/usr/local/share/aidesk/helper-app/aidesk-helper" "$PAYLOAD/usr/local/bin/aidesk-helper"

cp "$DESKTOP_AGENT/scripts/aidesk-action-hook.cjs" "$PAYLOAD/usr/local/share/aidesk/hooks/"
cp "$DESKTOP_AGENT/scripts/aidesk-prompt-hook.cjs" "$PAYLOAD/usr/local/share/aidesk/hooks/"
cp "$DESKTOP_AGENT/scripts/aidesk-compact-hook.cjs" "$PAYLOAD/usr/local/share/aidesk/hooks/"

# aidesk-channel mcp 서버 — bun compile standalone binary (rc20+: 외부 AI 와 통일).
# 옛 node + server.js + node_modules 패턴 → 단일 binary.
# node 의존 X + 외부 AI 의 bun binary 와 *같은 build* → fix 일관 적용.
AIDESK_CHANNEL_SRC="$(cd "$DESKTOP_AGENT/.." && pwd)/aidesk-channel"
if [[ -d "$AIDESK_CHANNEL_SRC" ]]; then
    mkdir -p "$PAYLOAD/usr/local/share/aidesk/aidesk-channel/bin"
    echo "→ bun build aidesk-channel binary (darwin-${ARCH})"
    pushd "$AIDESK_CHANNEL_SRC" > /dev/null
    bun install --production
    BUN_TARGET="bun-darwin-${ARCH}"
    bun build --compile --target="$BUN_TARGET" src/server.js \
        --outfile "$PAYLOAD/usr/local/share/aidesk/aidesk-channel/bin/aidesk-channel"
    popd > /dev/null
    chmod 755 "$PAYLOAD/usr/local/share/aidesk/aidesk-channel/bin/aidesk-channel"
else
    echo "⚠ aidesk-channel 소스 없음 — 건너뜀: $AIDESK_CHANNEL_SRC"
fi

# aidesk-bot-adapter — per-AI WebSocket bot adapter (PoC v1). helper bootstrap 이 spawn.
# aidesk-channel 과 같은 패턴 — node_modules 포함 같이 배포해서 사용자 mac 별도 npm install 불필요.
AIDESK_BOT_ADAPTER_SRC="$(cd "$DESKTOP_AGENT/.." && pwd)/aidesk-bot-adapter"
if [[ -d "$AIDESK_BOT_ADAPTER_SRC" ]]; then
    mkdir -p "$PAYLOAD/usr/local/share/aidesk/aidesk-bot-adapter"
    cp -R "$AIDESK_BOT_ADAPTER_SRC/bin" \
          "$AIDESK_BOT_ADAPTER_SRC/node_modules" \
          "$AIDESK_BOT_ADAPTER_SRC/package.json" \
          "$PAYLOAD/usr/local/share/aidesk/aidesk-bot-adapter/"
    chmod 755 "$PAYLOAD/usr/local/share/aidesk/aidesk-bot-adapter/bin/aidesk-bot-adapter"
else
    echo "⚠ aidesk-bot-adapter 소스 없음 — 건너뜀: $AIDESK_BOT_ADAPTER_SRC"
fi

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
