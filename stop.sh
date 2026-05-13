#!/bin/zsh
# AI Desk 로컬 종료 스크립트. 백엔드/프론트/code-server 모두 죽인다.
# 살아있는 tmux 세션이나 cmux 워크스페이스는 건드리지 않음.

for port in 30082 30081 30080; do
  pid="$(lsof -ti:"$port" -sTCP:LISTEN 2>/dev/null | head -1)"
  if [[ -n "$pid" ]]; then
    kill "$pid" && echo "✗ killed :$port (pid=$pid)"
  else
    echo "· :$port already free"
  fi
done
