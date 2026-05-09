# AI Desk — 작업 보드

> 큰 단위로 묶은 작업 진행 트래커. 세부 PR 단위는 `/Users/jsh/Documents/jsh/AI Desk/messages/implementation_plan.md` 참조.
> 화면 명세는 `/Users/jsh/Documents/jsh/AI Desk/{dashboard,messages,frame}/`.

## 범례
| 표기 | 의미 |
|---|---|
| ✅ | 완료 |
| 🟡 | 진행 중 |
| ⬜ | 미착수 |
| ⏸️ | 후순위 / 보류 |

---

## Phase 0 — 화면설계서 + 부트스트랩 ✅
> 코드 작성 전 합의·환경 준비 단계.

- ✅ 화면설계서 작성 — `dashboard/`, `messages/`, `frame/` 명세서 일체
- ✅ AI 협업 채널(D+C) 설계 — `messages_*.md`, `adesk_cli.md`, `implementation_plan.md`
- ✅ Spring Boot 프로젝트 리네임 (`com.jsh.aidesk.serverapi`, port 8081)
- ✅ Nuxt 4.3.1 SPA 스캐폴드 (port 3000, `apiBase=http://localhost:8081`)
- ✅ 단일 git repo + 루트 `.gitignore`
- ✅ 사전 준비 도구 점검 (tmux, Node 24, Java 21, Docker, Git)

---

## Phase 1 — 인프라 + 공통 모듈 🟡
> 도메인 코드 작성 전 양쪽 공통 토대.

### Backend ✅
- ✅ Docker PG에 `aidesk` 데이터베이스 생성
- ✅ `t_ai_agent` 스키마 + 시드 (`db/schema.sql` + `db/data.sql`, 행 3개)
- ✅ `build.gradle` 의존성 추가 (MyBatis 4.0.1 · PostgreSQL · POI · OpenAPI / **인증 관련 제외**)
- ✅ `application.yaml` + `application-dev.yaml` (dev only, port 8081, DB·CORS·MyBatis)
- ✅ 공통 모듈 작성 (**JWT/Security 제외**)
  - ✅ `common/response/` — ResponseJson, ResponseCode, CodeData
  - ✅ `common/util/DateUtil.java`
  - ⬜ `common/vo/` — 후속 단계에 도입 (현재 미사용)
  - ✅ `config/CorsConfig.java` (3000 허용)

### Frontend ✅
- ✅ Pinia 모듈 추가 (`@pinia/nuxt` + `pinia`)
- ✅ `plugins/api.ts` — `$api` (= $fetch + baseURL) 주입 (인증 인터셉터는 미포함)
- ✅ `layouts/default.vue` — 헤더(56+48px) + 사이드(245px) 조합
- ✅ `components/layout/HeaderView.vue`, `LeftMenuView.vue` (햄버거 토글, 활성 라우트, 미확인 뱃지 hook)
- ✅ 공통 CSS 마이그레이션 (`assets/css/reset.css`, `common.css`, `layout.css`)
- ✅ `stores/layout.ts` — 사이드 메뉴 열림/닫힘

---

## Phase 2 — 대시보드 화면 ⬜
> 첫 도메인. 인프라 검증을 겸함.

### Backend ✅
- ✅ `agents/` 도메인 4계층 (controller/service/mapper/vo)
- ✅ `GET /api/agents` (필터·요약카운트) — **검증 OK** (200, list + summary)
- ✅ `POST /api/agents` (생성, TMUX_SESSION 자동 부여) — **검증 OK** (UUID + 모델 풀네임 변환)
- ✅ `DELETE /api/agents/{agentId}` (소프트 딜리트) — **검증 OK** (deleted_at = NOW())
- ⬜ `GET /api/context` (JSONL 파싱) — Phase 4와 연계, 후순위

### Frontend ✅
- ✅ `pages/dashboard.vue` 스캐폴드 + index.vue 리다이렉트
- ✅ 페이지 헤더 (breadcrumb + AI 생성 버튼)
- ✅ 요약 카드 4종 (`SummaryCardGrid`)
- ✅ 필터 탭 + 검색 (`FilterBar`, status는 서버, query는 클라이언트 필터)
- ✅ AI 카드 그리드 (이모지 아바타·상태 컬러바·컨텍스트 바·메뉴 ⋮)
- ✅ AI 생성 팝업 (이름·워크스페이스·모델, 검증 + 정책 응답 처리)
- ✅ 카드 메뉴 드롭다운 (VSCode/터미널/검증/삭제 — *메시지 보내기는 Phase 3 후 연결*)
- ✅ 10초 폴링 (`startPolling` / `stopPolling` in `useAgents`)

### 검증 ✅
- ✅ Chrome MCP로 화면 동작 검증 — **M2 달성**
  - ✅ 페이지 진입 → 카드 그리드·요약·필터·검색 정상 렌더링
  - ✅ 필터 탭(작업중) → 1개만 표시
  - ✅ 검색("코드") → 코드 리뷰 AI만 표시
  - ✅ AI 생성 팝업 → 폼 입력 → 카드 즉시 추가 + 요약 갱신 (4·작업중 2)
  - ✅ 카드 메뉴 ⋮ → 5개 항목 (메시지 보내기 disabled, 삭제 destructive)
  - ✅ 삭제 확인 팝업 → 삭제 → 카드 사라짐 + 요약 갱신 + DB soft-delete
- 발견된 minor 이슈 :
  - 사이드 메뉴 `/logs`/`/messages`/`/settings` 라우터 경고 — Phase 3+ 페이지 추가 시 자연 해결
  - 마지막 row 카드의 ⋮ dropdown이 grid reflow를 유발 — 추후 dropdown 위치 조건부 조정으로 개선 가능

---

## Phase 3 — 메시지 화면 ✅
> AI 협업 채널 1단계 (D 단독, last mile 은 Phase 4).

### Backend ✅
- ✅ `t_ai_message` 스키마 + 인덱스 5종
- ✅ `messages/` 도메인 4계층 (controller / service / mapper / vo / policy / lastmile)
- ✅ `POST /api/messages` (정책 검사 + INSERT + last mile stub + 부모 자동 replied)
- ✅ `GET /api/messages` / `/conversations` (CTE roll-up) / `/unread-count`
- ✅ `PATCH /api/messages/{id}/read`
- ⬜ `PATCH /api/messages/{id}/reply` (POST + replyToMessageId 가 자동 처리하므로 후순위)
- ✅ `MessagePolicyChecker` (rate/hop/context guard/done guard)

### Frontend ✅
- ✅ `pages/messages.vue` (관점 AI 선택 + 대화 목록 320px + 타임라인 + 컴포저)
- ✅ `components/messages/NewMessageDialog.vue` (대시보드 카드 메뉴 + 메시지 페이지 헤더 공유)
- ✅ 발신 버블 상태 라벨 (sent/delivered/replied/failed)
- ✅ 미확인 뱃지 (대시보드 카드 + 사이드 메뉴 totalUnread)
- ✅ 카드 메뉴 "메시지 보내기" 항목 연결 (받는 AI 사전 선택 + 잠금)

### 검증 ✅
- ✅ POST/GET/PATCH curl 검증 (정상 발신·정책 거절·self-message·답장 체인·conversations·unread-count·read)
- ✅ Chrome MCP: 관점 AI 선택 → 대화 진입 → 자동 read → 메시지 발신(이모지 포함) → 좌측 미리보기 갱신 — **M3 달성**
- ✅ Chrome MCP: 대시보드 카드 메뉴 → 새 메시지 팝업 → 발신 → 사이드/카드 뱃지 자동 갱신

---

## Phase 4 — Last Mile + 스케줄러 🟡
> 실제 AI 세션과 연동하여 한 방향 전달 자동화.

- ✅ `TmuxLastMileAdapter` (`tmux has-session`/`send-keys`) — @Primary 로 stub 대체
- ✅ 메시지 헤더 컨벤션 렌더 (`[aidesk · FROM:.. | MSG:..] {content}  ↳ 응답: adesk reply ...`)
- ✅ 비동기 처리 (Java 21 virtual thread — `Thread.startVirtualThread`)
- ⬜ `adesk` CLI 1차 (`whoami` / `reply`) — Node.js 별도 패키지, 다음 라운드
- ✅ 세션 파일 감지 스케줄러 (`@Scheduled(fixedDelay=10_000, initialDelay=5_000)` + AgentStatusWatcher) — claude 모델 한정
- ✅ 컨텍스트 사용량 자동 갱신 (`~/.claude/projects/**/*.jsonl` 파싱, message.usage → tokens / 1M)

---

## Phase 5 — D + C 결합 (자율 협업) ⏸️
> AI가 도구 호출로 능동 발신/응답 가능하도록.

- ⬜ `aidesk-channel/` MCP 서버 별도 패키지 (Node.js)
- ⬜ MCP 도구 4종 — `send_to` / `reply` / `check_inbox` / `list_agents`
- ⬜ `<channel>` 푸시 형식 구현
- ⬜ `McpLastMileAdapter` (tmux fallback 유지)
- ⬜ 양쪽 AI mcp.json 등록 가이드

---

## Phase 6 — 멀티 AI / 운영 안정화 ⏸️
> 1:1 → 1:N → 그룹 → 정책·시각화.

- ⬜ `T_AI_MESSAGE_RECEIPT` (멀티캐스트)
- ⬜ `T_AI_ROOM*` (그룹 대화)
- ⬜ 권한 정책 (rate limit / hop count 강화)
- ⬜ 메시지 트리 시각화 (대시보드)
- ⬜ 감사 로그 화면

---

## 마일스톤

| 코드 | 정의 | 의존 Phase |
|---|---|---|
| M1 | 백엔드 부팅 + `GET /api/agents` 200 | Phase 1 |
| M2 | 대시보드 화면 동작 (CRUD 일체) | Phase 2 |
| M3 | 메시지 화면 동작 (수동 등록) | Phase 3 |
| M4 | 양방향 자동 (tmux + adesk reply) | Phase 4 |
| M5 | 자율 협업 (MCP 도구) | Phase 5 |

---

## 변경 이력
- 2026-05-09 : 보드 초기 작성 (Phase 0 완료, Phase 1 착수)
- 2026-05-09 : Phase 1 백엔드 완료, Phase 2 백엔드 agents 도메인 3종 엔드포인트 작성 + GET 검증 — **M1 달성**
- 2026-05-09 : Phase 1 프론트(Pinia·layout·CSS·api) + Phase 2 프론트(요약/필터/카드/생성/삭제) 완료. POST/DELETE 검증 OK.
- 2026-05-09 : Chrome MCP 시각 검증 통과 (필터·검색·생성·메뉴·삭제 전체 동작) — **M2 달성**
- 2026-05-09 : Phase 3 백엔드 완료 (messages 도메인 + 정책 + last mile stub + read/conversations/unread-count)
- 2026-05-09 : Phase 3 프론트 완료 (메시지 페이지 + NewMessageDialog + 사이드/카드 뱃지 + 카드 메뉴 활성화). Chrome MCP 시각 검증 통과 — **M3 달성**
- 2026-05-09 : Phase 4 백엔드 3종 완료 (TmuxLastMileAdapter + virtual thread + AgentStatusWatcher + jsonl context_pct 파싱). 실제 tmux 세션 도착·세션 부재 failed·context 0→74% 자동 갱신 검증. 남은 건 adesk CLI.
