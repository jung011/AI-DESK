#!/bin/bash
# AI Desk Helper *DEV* macOS .pkg 빌드 스크립트.
#
# prod 빌드 (build.sh) 와 *모든 식별자 분리*. 같은 mac 에 prod + dev .pkg 동시 install 가능,
# 둘이 서로 자리 안 덮어씀.
#
# 사용:
#   ./build-pkg/build-dev.sh               # 버전 dev-0.1.0 으로 빌드
#   VERSION=dev-0.2.0 ./build-pkg/build-dev.sh
#
# 산출물: build-pkg/dist/AIDeskHelperDev-${VERSION}-${ARCH}.pkg
#
# 분리 항목:
#   PKG_ID              com.kaflix.aidesk-helper-dev
#   install dir         /usr/local/share/aidesk-dev/
#   /usr/local/bin      aidesk-helper-dev (symlink)
#   LaunchAgent label   com.aidesk.agent.dev
#   plist path          ~/Library/LaunchAgents/com.aidesk.agent.dev.plist
#   port                30084
#   AIDESK_HUB_URL      http://localhost:30081 (dev backend)
#   log path            ~/Library/Logs/aidesk-agent-dev.{err,log}

set -euo pipefail

VERSION="${VERSION:-dev-0.1.0}"
ARCH="$(uname -m)"
PKG_ID="com.kaflix.aidesk-helper-dev"

ROOT="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_AGENT="$(cd "$ROOT/.." && pwd)"
BUILD="$ROOT/build-dev"
DIST="$ROOT/dist"
PAYLOAD="$BUILD/payload"

echo "→ Cleaning build-dev/"
rm -rf "$BUILD"
mkdir -p "$BUILD" "$DIST"

# zellij 다운로드 — build.sh 와 동일 cache 공유 (desktop-agent/bin/zellij).
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
    echo "→ zellij v${ZELLIJ_VERSION} (${ZELLIJ_TARGET}) 다운로드"
    mkdir -p "$DESKTOP_AGENT/bin"
    curl -fSL --max-time 120 \
        "https://github.com/zellij-org/zellij/releases/download/v${ZELLIJ_VERSION}/zellij-${ZELLIJ_TARGET}.tar.gz" \
        -o "$DESKTOP_AGENT/bin/zellij.tar.gz"
    tar -xzf "$DESKTOP_AGENT/bin/zellij.tar.gz" -C "$DESKTOP_AGENT/bin"
    rm "$DESKTOP_AGENT/bin/zellij.tar.gz"
    chmod +x "$ZELLIJ_BIN"
    xattr -d com.apple.quarantine "$ZELLIJ_BIN" 2>/dev/null || true
    codesign --force --sign - "$ZELLIJ_BIN" 2>/dev/null || true
fi
echo "  zellij: $("$ZELLIJ_BIN" --version)"

echo "→ [1/4] Running PyInstaller (dev)"
cd "$DESKTOP_AGENT"
uv run pyinstaller \
    --clean --noconfirm \
    --distpath "$BUILD/pyi-dist" \
    --workpath "$BUILD/pyi-work" \
    "$ROOT/aidesk-helper.spec"

HELPER_DIR="$BUILD/pyi-dist/aidesk-helper"
[[ -d "$HELPER_DIR" && -x "$HELPER_DIR/aidesk-helper" ]] || { echo "✗ PyInstaller onedir not found: $HELPER_DIR"; exit 1; }

echo "→ [2/4] Composing payload (dev — separate install location)"
mkdir -p "$PAYLOAD/usr/local/bin"
mkdir -p "$PAYLOAD/usr/local/share/aidesk-dev/hooks"
mkdir -p "$PAYLOAD/usr/local/share/aidesk-dev/helper-app"

cp -R "$HELPER_DIR"/. "$PAYLOAD/usr/local/share/aidesk-dev/helper-app/"
chmod 755 "$PAYLOAD/usr/local/share/aidesk-dev/helper-app/aidesk-helper"

# /usr/local/bin/aidesk-helper-dev — prod 의 aidesk-helper 와 별도 이름
ln -sf "/usr/local/share/aidesk-dev/helper-app/aidesk-helper" "$PAYLOAD/usr/local/bin/aidesk-helper-dev"

cp "$DESKTOP_AGENT/scripts/aidesk-action-hook.cjs" "$PAYLOAD/usr/local/share/aidesk-dev/hooks/"
cp "$DESKTOP_AGENT/scripts/aidesk-prompt-hook.cjs" "$PAYLOAD/usr/local/share/aidesk-dev/hooks/"
cp "$DESKTOP_AGENT/scripts/aidesk-compact-hook.cjs" "$PAYLOAD/usr/local/share/aidesk-dev/hooks/"

# aidesk-channel mcp — prod 와 동일 (bun compile binary). 단 install location 만 dev.
AIDESK_CHANNEL_SRC="$(cd "$DESKTOP_AGENT/.." && pwd)/aidesk-channel"
if [[ -d "$AIDESK_CHANNEL_SRC" ]]; then
    mkdir -p "$PAYLOAD/usr/local/share/aidesk-dev/aidesk-channel/bin"
    echo "→ bun build aidesk-channel binary (darwin-${ARCH}) — dev"
    pushd "$AIDESK_CHANNEL_SRC" > /dev/null
    bun install --production
    BUN_TARGET="bun-darwin-${ARCH}"
    bun build --compile --target="$BUN_TARGET" src/server.js \
        --outfile "$PAYLOAD/usr/local/share/aidesk-dev/aidesk-channel/bin/aidesk-channel"
    popd > /dev/null
    chmod 755 "$PAYLOAD/usr/local/share/aidesk-dev/aidesk-channel/bin/aidesk-channel"
fi

AIDESK_BOT_ADAPTER_SRC="$(cd "$DESKTOP_AGENT/.." && pwd)/aidesk-bot-adapter"
if [[ -d "$AIDESK_BOT_ADAPTER_SRC" ]]; then
    mkdir -p "$PAYLOAD/usr/local/share/aidesk-dev/aidesk-bot-adapter"
    cp -R "$AIDESK_BOT_ADAPTER_SRC/bin" \
          "$AIDESK_BOT_ADAPTER_SRC/node_modules" \
          "$AIDESK_BOT_ADAPTER_SRC/package.json" \
          "$PAYLOAD/usr/local/share/aidesk-dev/aidesk-bot-adapter/"
    chmod 755 "$PAYLOAD/usr/local/share/aidesk-dev/aidesk-bot-adapter/bin/aidesk-bot-adapter"
fi

STATUSLINE_SRC="$(cd "$DESKTOP_AGENT/.." && pwd)/adesk-cli/bin/aidesk-statusline.cjs"
if [[ -f "$STATUSLINE_SRC" ]]; then
    cp "$STATUSLINE_SRC" "$PAYLOAD/usr/local/share/aidesk-dev/hooks/"
fi

chmod 755 "$PAYLOAD/usr/local/share/aidesk-dev/hooks/"*.cjs

# 설치 스크립트 (dev 전용)
chmod 755 "$ROOT/scripts-dev/postinstall"

echo "→ [3/4] pkgbuild (dev component)"
pkgbuild \
    --root "$PAYLOAD" \
    --scripts "$ROOT/scripts-dev" \
    --identifier "$PKG_ID" \
    --version "$VERSION" \
    --install-location / \
    "$BUILD/AIDeskHelperDev-component.pkg"

echo "→ [4/4] productbuild (distribution)"
OUT="$DIST/AIDeskHelperDev-${VERSION}-${ARCH}.pkg"
productbuild \
    --identifier "$PKG_ID" \
    --version "$VERSION" \
    --package "$BUILD/AIDeskHelperDev-component.pkg" \
    "$OUT"

echo ""
echo "✓ Built (dev): $OUT"
echo ""
echo "설치:"
echo "  sudo installer -pkg \"$OUT\" -target /"
echo ""
echo "확인:"
echo "  launchctl list | grep com.aidesk.agent.dev"
echo "  tail -f ~/Library/Logs/aidesk-agent-dev.err"
echo "  curl http://localhost:30084/api/health"
