"""`python -m aidesk_agent` 또는 `aidesk-agent` 진입점.

CLI 인자 / env (dev/prod 분리 인스턴스 지원):
- `--port N` (또는 `AIDESK_HELPER_PORT=N`) — 기본 30083. dev 분리 시 30084 등.
- `--hub-url URL` (또는 `AIDESK_HUB_URL=URL`) — backend hub URL override.

dev helper 분리 실행 예:
    AIDESK_HUB_URL=http://localhost:30081 \
    .venv/bin/python -m aidesk_agent --port 30084
"""
from __future__ import annotations

import argparse
import os

from .server import DEFAULT_HOST, DEFAULT_PORT, run


def main() -> None:
    p = argparse.ArgumentParser(prog="aidesk-agent", description="AI Desk helper")
    p.add_argument("--host", default=os.environ.get("AIDESK_HELPER_HOST", DEFAULT_HOST))
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AIDESK_HELPER_PORT", DEFAULT_PORT)),
    )
    p.add_argument("--hub-url", dest="hub_url", default=None,
                   help="AIDESK_HUB_URL env override")
    args = p.parse_args()
    if args.hub_url:
        os.environ["AIDESK_HUB_URL"] = args.hub_url
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
