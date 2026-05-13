#!/bin/zsh
# AI Desk 로컬 시작 스크립트.
# 백엔드(:30081) + 프론트(:30080) + code-server(:30082) 를 백그라운드로 띄운다.
# 로그는 /tmp 에 떨어뜨려 tail 로 추적 가능.
#
# 사용: ./start.sh
# 종료: 각 포트의 프로세스를 kill — `./stop.sh` 또는
#        `lsof -ti:30081 -sTCP:LISTEN | xargs kill` (포트별)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

is_listening() {
  lsof -ti:"$1" -sTCP:LISTEN > /dev/null 2>&1
}

# 백엔드 (Spring Boot, 30081)
if is_listening 30081; then
  echo "↺ backend already running on :30081"
else
  ( cd "$ROOT/backend" && ./gradlew bootRun --args="--spring.profiles.active=dev" \
      > /tmp/aidesk-backend.log 2>&1 & )
  echo "▶ backend  starting → /tmp/aidesk-backend.log"
fi

# 프론트 (Nuxt dev, 30080)
if is_listening 30080; then
  echo "↺ frontend already running on :30080"
else
  ( cd "$ROOT/frontend" && npm run dev \
      > /tmp/aidesk-frontend.log 2>&1 & )
  echo "▶ frontend starting → /tmp/aidesk-frontend.log"
fi

# code-server (대시보드 임베드 VSCode, :30082)
# --auth none 으로 로컬 사용 가정. 외부 노출하려면 password 인증 필수.
if is_listening 30082; then
  echo "↺ code-server already running on :30082"
elif ! command -v code-server > /dev/null 2>&1; then
  echo "⚠ code-server 미설치 — brew install code-server 후 다시 실행하세요 (VSCode 임베드 비활성)"
else
  ( code-server --auth none --bind-addr 127.0.0.1:30082 --disable-telemetry --disable-update-check \
      > /tmp/aidesk-codeserver.log 2>&1 & )
  echo "▶ code-server starting → /tmp/aidesk-codeserver.log"
fi

echo ""
echo "  대시보드 : http://localhost:30080/dashboard"
echo "  백엔드 API: http://localhost:30081/api/agents"
echo "  code-server : http://localhost:30082/"
