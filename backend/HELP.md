# AI Desk Server API

Claude Code AI 에이전트 모니터링 + 협업 채널 백엔드.

## 환경
- Java 21 (toolchain)
- Spring Boot 4.0.5
- Build : Gradle (`gradlew`)

## 패키지 구조
- 루트 패키지 : `com.jsh.aidesk.serverapi`
- 메인 클래스 : `AiDeskApplication`

## 빌드 / 실행
```bash
./gradlew bootRun           # 개발 실행
./gradlew build             # 빌드
./gradlew test              # 테스트
```

## 기획·명세서
- 화면설계서 : `/Users/jsh/Documents/jsh/AI Desk/`
- 백엔드 명세 : `dashboard/dashboard_backend.md`, `messages/messages_backend.md`
- 공통 API 명세 : `dashboard/dashboard_common.md`, `messages/messages_common.md`

## 참고 — Spring Boot 4 / Spring Cloud 2025.1
- `spring-boot-starter-webmvc` (Boot 4의 새 모듈명, 기존 `-web` 대체)
- `spring-cloud-starter-openfeign`
- Validation, Lombok 포함
