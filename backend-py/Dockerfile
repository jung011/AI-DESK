# multi-stage 빌드 — uv 로 deps 설치 후 slim runtime 에 복사.
# 주의: builder/runtime 의 venv 경로를 *동일* 하게 (/app) — shebang 의 python path 가 venv
# 안에 hard-coded 되어 stage 가 바뀌면 깨짐.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./


FROM python:3.12-slim AS runtime

RUN mkdir -p /app/helper

WORKDIR /app

# builder 와 runtime 의 path 동일 (/app/.venv) — shebang hard-coded 호환
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini

# helper .pkg image 에 baked. 갱신 시 backend-py/helper-pkg/ 교체 + image rebuild
COPY helper-pkg /app/helper

# 외부 AI mcp standalone binary (darwin-arm64 / linux-x64 / linux-arm64) — git 없는
# 외부 운영 환경 download path. 갱신 시 backend-py/static/mcp/ 교체 + image rebuild.
COPY static /app/static

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# helm chart 의 backend.port = 30081 (Spring 시절 그대로). containerPort + readinessProbe
# tcpSocket: port http → service.targetPort 까지 다 30081 매핑. FastAPI 도 같은 port 사용.
EXPOSE 30081

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "30081"]
