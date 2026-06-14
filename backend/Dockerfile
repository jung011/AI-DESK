# syntax=docker/dockerfile:1.7
# Backend (Spring Boot) — multi-stage 빌드 + Spring Boot Layered JAR.
#
# 1단계: Eclipse Temurin JDK 21 + gradlew 로 부트 JAR 생성 + layertools 로 분리
# 2단계: JRE 21 만 담은 slim 이미지에 layer 별로 COPY (의존성/loader/snapshot/application)
#         → 코드만 바뀌면 application layer 만 재빌드, 의존성 layer cache hit.
#
# 빌드 시 BuildKit cache mount (/root/.gradle) 사용 — gradle deps + build cache 보존.
#
# 빌드: `docker build -t aidesk-backend .` (backend/ 디렉토리에서)
# 실행: `docker run --rm -p 30081:30081 aidesk-backend`

# ────────────────────────────────────────────────────────────────────────────────
# Stage 1: build
# ────────────────────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

# 의존성 캐시 위해 gradle wrapper + 빌드 스크립트만 먼저 복사
COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew --version > /dev/null

# 소스 + 리소스 복사 후 빌드. --mount=type=cache 로 ~/.gradle 보존 → deps 재 download skip.
COPY src ./src
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon bootJar --build-cache -x test

# Spring Boot Layered JAR — layer 별 분리해서 layer 디렉토리로 추출.
# 다음 stage 에서 의존성 layer 부터 application layer 까지 순서대로 COPY 하면
# 의존성 안 바뀐 build 는 cache hit, application classes 만 재 build.
RUN java -Djarmode=layertools -jar build/libs/*.jar extract --destination layers

# ────────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
# ────────────────────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre AS runtime
WORKDIR /app

# Non-root 사용자 (보안 + Docker best practice)
RUN groupadd -r aidesk && useradd -r -g aidesk -d /app aidesk

# Spring Boot layer 순서대로 COPY — 변경 빈도 적은 layer 먼저.
COPY --from=build /workspace/layers/dependencies/ ./
COPY --from=build /workspace/layers/spring-boot-loader/ ./
COPY --from=build /workspace/layers/snapshot-dependencies/ ./
COPY --from=build /workspace/layers/application/ ./

# helper .pkg 도 image 에 함께 baked — HelperDownloadController 가 인증 후 서빙.
# .pkg 갱신 시 backend/helper-pkg/ 의 옛 파일 교체 + image rebuild.
COPY helper-pkg /app/helper
RUN chown -R aidesk:aidesk /app
USER aidesk

EXPOSE 30081

# Layered JAR launcher — main class 자동 detect. -jar 대신 launcher class 사용.
# Spring 환경변수로 모든 설정 override 가능. docker-compose 가 SPRING_DATASOURCE_URL 등 주입.
ENTRYPOINT ["java", "-Djava.net.useSystemProxies=false", "org.springframework.boot.loader.launch.JarLauncher"]
