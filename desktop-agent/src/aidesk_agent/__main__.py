"""`python -m aidesk_agent` 또는 `aidesk-agent` 진입점."""
from __future__ import annotations

from .server import DEFAULT_HOST, DEFAULT_PORT, run


def main() -> None:
    run(host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":
    main()
