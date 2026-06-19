# aidesk-backend (FastAPI)

AI Desk backend — Spring Boot 의 FastAPI 마이그.

> 진행 중인 작업. 기존 `backend/` 와 *병행 운영* 상태 — 안정화 후 `backend/` 제거 예정.

## 디렉토리

```
app/
├── main.py              # FastAPI entry + router 등록
├── core/                # config / database / security / exceptions / middleware
├── common/              # 공통 응답 envelope
├── auth/                # /api/auth — login, signup, JWT
├── agents/              # /api/agents + /api/agents/external + watcher
├── messages/            # /api/messages + SSE
├── desktop/             # /api/desktop — helper local-info
├── helper/              # /api/helper — .pkg download
├── colleagues/          # /api/colleagues — 휴먼 entity
├── logs/                # /api/logs + /api/action-logs
└── settings/            # /api/settings

alembic/                 # DB migration (codegen 만)
tests/                   # pytest
```

자세한 설계 = [패키지 구성.md](../../../AI Desk/FastAPI 마이그/패키지 구성.md)
endpoint 목록 = [endpoint 카탈로그.md](../../../AI Desk/FastAPI 마이그/endpoint 카탈로그.md)

## 개발

```bash
# 의존성 설치
uv sync

# 로컬 실행 (dev — auto reload)
uv run uvicorn app.main:app --reload --port 8080

# 테스트
uv run pytest

# lint + format
uv run ruff check .
uv run ruff format .

# type check
uv run pyright
```

## 환경 변수 (`.env`)

```
DB_URL=mysql+pymysql://aidesk:***@db:3306/aidesk
JWT_SECRET_KEY=...
CORS_ALLOWED_ORIGINS=["http://aidesk.kaflix.internal"]
HELPER_PKG_DIR=/app/helper
MESSAGE_CONTEXT_LIMIT_PCT=90
MESSAGE_HOP_LIMIT=10
```

helm `aidesk-ai-desk` ConfigMap + Secret 의 env 가 그대로 매핑.

## 마이그 진척

| 도메인 | 상태 |
|---|---|
| core (config / database / security / exceptions / middleware) | 🚧 진행 |
| auth | 🚧 진행 |
| settings | ⏳ 대기 |
| helper | ⏳ 대기 |
| colleagues | ⏳ 대기 |
| agents | ⏳ 대기 |
| desktop | ⏳ 대기 |
| messages | ⏳ 대기 |
| agents/external | ⏳ 대기 |
| logs | ⏳ 대기 |
