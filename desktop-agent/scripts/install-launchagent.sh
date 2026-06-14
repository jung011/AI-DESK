#!/bin/zsh
# AI Desk Helper LaunchAgent 설치 스크립트.
#
# templates/com.aidesk.agent.plist 의 {{HOME}}/{{AGENT_DIR}} 을 현재 사용자 환경
# 으로 치환해 ~/Library/LaunchAgents/ 에 배치하고 launchctl 로 load 한다.
#
# 사용: desktop-agent/ 디렉토리에서  ./scripts/install-launchagent.sh
# 제거:                              ./scripts/install-launchagent.sh --uninstall

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$AGENT_DIR/templates/com.aidesk.agent.plist"
TARGET="$HOME/Library/LaunchAgents/com.aidesk.agent.plist"

uninstall() {
  if [[ -f "$TARGET" ]]; then
    launchctl unload "$TARGET" 2>/dev/null || true
    rm "$TARGET"
    echo "✗ uninstalled $TARGET"
  else
    echo "(이미 미설치)"
  fi
}

install() {
  [[ -f "$TEMPLATE" ]] || { echo "템플릿이 없습니다: $TEMPLATE"; exit 1; }
  command -v "$HOME/.local/bin/uv" > /dev/null || \
    { echo "⚠ uv 가 ~/.local/bin/uv 에 없음. uv 설치 후 재실행하세요."; exit 1; }

  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

  sed -e "s#{{HOME}}#$HOME#g" \
      -e "s#{{AGENT_DIR}}#$AGENT_DIR#g" \
      "$TEMPLATE" > "$TARGET"

  # 이미 로드되어 있으면 깔끔하게 unload 후 다시 load (변경 사항 즉시 반영)
  launchctl unload "$TARGET" 2>/dev/null || true
  launchctl load "$TARGET"

  echo "✓ installed: $TARGET"
  echo "  AGENT_DIR: $AGENT_DIR"
  echo ""
  echo "확인:    launchctl list | grep com.aidesk.agent"
  echo "로그:    tail -f ~/Library/Logs/aidesk-agent.err"
  echo "제거:    $0 --uninstall"
}

case "${1:-install}" in
  --uninstall|uninstall) uninstall ;;
  *)                     install ;;
esac
