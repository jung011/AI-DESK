# syntax=docker/dockerfile:1.7
# Backend (Spring Boot) — multi-stage 빌드.
#
# 1단계: Eclipse Temurin JDK 21 + gradlew 로 부트 JAR 생성
# 2단계: JRE 21 만 담은 slim 이미지에 JAR 만 복사
#
# 빌드: `docker build -t aidesk-backend .` (backend/ 디렉토리에서)
# 실행: `docker run --rm -p 30081:30081 aidesk-backend`
#       (DB 는 호스트의 host.docker.internal:5432 로 접근 — env 로 override 가능)

# ────────────────────────────────────────────────────────────────────────────────
# Stage 1: build
# ────────────────────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

# 의존성 캐시를 살리기 위해 gradle wrapper + 빌드 스크립트만 먼저 복사
COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew --version > /dev/null

# 소스 + 리소스 복사 후 빌드
COPY src ./src
RUN ./gradlew --no-daemon bootJar -x test

# ────────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
# ────────────────────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre AS runtime
WORKDIR /app

# Non-root 사용자 (보안 + Docker best practice)
RUN groupadd -r aidesk && useradd -r -g aidesk -d /app aidesk

COPY --from=build /workspace/build/libs/*.jar app.jar
# helper .pkg 도 image 에 함께 baked — HelperDownloadController 가 인증 후 서빙.
# .pkg 갱신 시 backend/helper-pkg/ 의 옛 파일 교체 + image rebuild.
COPY helper-pkg /app/helper
RUN chown -R aidesk:aidesk /app
USER aidesk

EXPOSE 30081

# Spring 환경변수로 모든 설정 override 가능. docker-compose 가 SPRING_DATASOURCE_URL,
# KAFLIX_CONTROL_PLANE_URL, KAFLIX_ME_EMPLOYEE_ID 등을 주입한다.
# 시스템 프록시 자동 감지는 컨테이너 안에선 불필요하지만 안전을 위해 끔.
ENTRYPOINT ["java", "-Djava.net.useSystemProxies=false", "-jar", "/app/app.jar"]
