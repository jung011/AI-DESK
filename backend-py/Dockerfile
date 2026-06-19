# multi-stage 빌드 — uv 로 deps 설치 후 slim runtime 에 복사
FROM python:3.12-slim AS builder

# uv 설치 (helper 와 stack 통일)
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /usr/local/bin/uv

WORKDIR /build
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./


FROM python:3.12-slim AS runtime

# helper .pkg 가 박힐 위치 — HelperDownloadController.locatePkg 와 호환
RUN mkdir -p /app/helper

WORKDIR /app

# uv 가 만든 venv 통째로 복사
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/app /app/app
COPY --from=builder /build/alembic /app/alembic
COPY --from=builder /build/alembic.ini /app/alembic.ini

# .pkg 도 image 에 함께 baked — backend 의 helper-pkg/ 폴더가 옛 Spring 과 동일 위치
# .pkg 갱신 시 backend-py/helper-pkg/ 의 옛 파일 교체 + image rebuild
COPY helper-pkg /app/helper

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8080

# 단일 worker (PoC). multi worker 필요 시 gunicorn -k uvicorn.workers.UvicornWorker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
