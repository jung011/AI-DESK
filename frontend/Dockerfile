# syntax=docker/dockerfile:1.7
# Frontend (Nuxt, SPA 모드) — multi-stage 빌드.
#
# same-origin proxy 패턴:
#   NUXT_PUBLIC_API_BASE 는 빈 문자열로 baked-in → 브라우저가 상대 경로(/api/...)로 호출.
#   nginx 가 같은 origin 안에서 /api/* 를 backend 컨테이너로 reverse proxy.
#   → 어떤 호스트(localhost / LAN IP / 모바일) 로 접속해도 동작. CORS 도 불필요.
#
# Helper 베이스만 baked-in (사용자 PC 의 http://localhost:30083). 모바일에선 helper 의존 기능 X.

FROM node:22-alpine AS build
WORKDIR /workspace

# API base 는 빈 문자열 → 상대 경로로 호출 → nginx 가 /api/* 를 backend 로 proxy.
ARG NUXT_PUBLIC_API_BASE=
ARG NUXT_PUBLIC_HELPER_BASE=http://localhost:30083
# subpath 배포 (예: ingress 가 https://도메인/ai-desk 로 노출) 지원.
# - app.baseURL 이 박혀서 모든 chunk/route 가 그 prefix 로 생성.
# - NUXT_PUBLIC_API_BASE 도 같은 prefix (예: /ai-desk) 로 주입 → $api 가 자동으로 prefix.
# - 기본값 '/' = root path 배포 (옛 동작).
# 빌드 예: docker build --build-arg NUXT_APP_BASE_URL=/ai-desk/ \
#                       --build-arg NUXT_PUBLIC_API_BASE=/ai-desk ...
ARG NUXT_APP_BASE_URL=/
ENV NUXT_PUBLIC_API_BASE=$NUXT_PUBLIC_API_BASE
ENV NUXT_PUBLIC_HELPER_BASE=$NUXT_PUBLIC_HELPER_BASE
ENV NUXT_APP_BASE_URL=$NUXT_APP_BASE_URL
# NUXT_PUBLIC_METAVERSE_URL 은 build-arg 가 아닌 *runtime env* — runtime stage 의 envsubst 가
# config.js 안에 치환해서 SPA 에 주입한다. 빌드 한 번 + 환경별 URL 갱신 가능.

# postinstall(nuxt prepare) 가 소스를 참조하므로 일괄 복사 후 install.
COPY . .
RUN npm install --no-audit --no-fund
# `nuxt generate` 가 정적 SPA shell (index.html 포함) 까지 .output/public 에 만든다.
# `nuxt build` (default) 는 SPA 모드에서 Nitro 서버에 의존하므로 nginx 만으로 못 서빙.
RUN npm run generate

# PWA manifest 안의 __BASE_URL__ placeholder 를 빌드 baseURL 로 치환.
# root 배포: /chat, /, /favicon.ico ↔ subpath 배포: /ai-desk/chat, /ai-desk/, /ai-desk/favicon.ico
RUN sed -i "s|__BASE_URL__|${NUXT_APP_BASE_URL}|g" .output/public/manifest.webmanifest

# ────────────────────────────────────────────────────────────────────────────────
# 정적 호스팅 (nginx) + /api/* same-origin reverse proxy
# ────────────────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# envsubst 는 alpine 의 gettext 패키지 안에 들어 있다.
RUN apk add --no-cache gettext

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/.output/public /usr/share/nginx/html

# config.js.template 은 build stage 가 .output/public 으로 복사하지 않으므로 별도 source 디렉토리에 둠.
COPY public/config.js.template /etc/templates/config.js.template

# 컨테이너 시작 시 환경변수 (예: METAVERSE_URL) 를 config.js 에 치환 후 nginx 기동.
# 미설정 env 는 빈 문자열로 치환 → SPA 가 hide 처리.
RUN { \
      echo '#!/bin/sh'; \
      echo 'set -e'; \
      echo 'envsubst < /etc/templates/config.js.template > /usr/share/nginx/html/config.js'; \
      echo 'exec nginx -g "daemon off;"'; \
    } > /docker-entrypoint.d/99-runtime-config.sh && chmod +x /docker-entrypoint.d/99-runtime-config.sh

EXPOSE 80
