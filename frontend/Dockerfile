# syntax=docker/dockerfile:1.7
# Frontend (Nuxt, SPA 모드) — multi-stage 빌드.
#
# Nuxt 의 runtimeConfig.public 값은 빌드 시점에 환경변수로 baked-in 된다:
#   NUXT_PUBLIC_API_BASE     — 백엔드 베이스 URL
#   NUXT_PUBLIC_HELPER_BASE  — 헬퍼 베이스 URL (사용자 PC 의 http://localhost:30083)

FROM node:22-alpine AS build
WORKDIR /workspace

# 빌드 시점에 baked-in 될 runtime config
ARG NUXT_PUBLIC_API_BASE=http://localhost:30081
ARG NUXT_PUBLIC_HELPER_BASE=http://localhost:30083
ENV NUXT_PUBLIC_API_BASE=$NUXT_PUBLIC_API_BASE
ENV NUXT_PUBLIC_HELPER_BASE=$NUXT_PUBLIC_HELPER_BASE

# postinstall(nuxt prepare) 가 소스를 참조하므로 일괄 복사 후 install.
COPY . .
RUN npm install --no-audit --no-fund
# `nuxt generate` 가 정적 SPA shell (index.html 포함) 까지 .output/public 에 만든다.
# `nuxt build` (default) 는 SPA 모드에서 Nitro 서버에 의존하므로 nginx 만으로 못 서빙.
RUN npm run generate

# ────────────────────────────────────────────────────────────────────────────────
# 정적 호스팅 (nginx)
# ────────────────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Nuxt SPA fallback (모든 미매칭 경로 → index.html).
# - absolute_redirect off  : 컨테이너 내부 포트(80) 가 Location 헤더에 박혀 외부 포트(30080) 가
#                            증발하는 문제를 회피. 상대 redirect 로 응답해 브라우저가 현재 origin 보존.
# - try_files $uri /index.html : 디렉토리 매칭 시도(=$uri/) 를 빼서 trailing-slash redirect 자체를 안 일으킴.
RUN printf 'server {\n  listen 80;\n  root /usr/share/nginx/html;\n  index index.html;\n  absolute_redirect off;\n  location / { try_files $uri /index.html; }\n}\n' > /etc/nginx/conf.d/default.conf

COPY --from=build /workspace/.output/public /usr/share/nginx/html

EXPOSE 80
