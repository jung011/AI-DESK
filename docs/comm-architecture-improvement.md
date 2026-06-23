# 통신 구조 개선 제안 — 연결 churn 감소 & 재부팅 의존 완화

> 작성일: 2026-06-24
> 대상: backend-py / desktop-agent(helper) / aidesk-channel 담당 개발자
> 상태: **제안(검증 전).** "확정 사실"과 "제안 변경"을 구분해 표기.
> 전제 환경: **로컬 머신당 10개 이상의 에이전트** 동시 운용.

---

## 1. 배경 — "주기적 PC 재부팅"의 진짜 원인

증상: 에이전트를 10개 이상 띄워 운용하면 시간이 갈수록 로컬 리소스가 누적되어 주기적으로
PC 재부팅이 필요하다.

조사 결론(마스터 기준):

- **누수성 원인은 이미 대부분 수정됨** (rc45~rc53):
  - DB 커넥션 풀 고갈(idle in transaction) — watcher rollback 누락(rc45), StreamingResponse
    미commit(rc47), N+1 + read-only 미commit(rc50)
  - asyncio/ws/task 누수 12-finding 정리(rc46), pty zombie 정리(helper 0.8.17),
    helper inbound/outbound 좀비 self-kill watchdog(0.8.18)
- **재부팅이 여전히 필요한 환원 불가능한 원인 = 커널 네트워크 상태 누적**:
  `cleanup.py` docstring 명시 — *"진짜 kernel state (pf table / NAT / TIME_WAIT) reset 은
  mac restart 만 답. 이 모듈은 process 잔재와 cache flush 까지만 cover."*

**핵심**: 커널 네트워크 테이블(TIME_WAIT 소켓 / pf 상태 / NAT 매핑)을 채우는 동력은
**연결 churn(연결을 자주 열고 닫는 것)** 이다. 연결을 *가지고 있는 것*이 아니라 *반복 생성·종료*가
문제다. 따라서 **churn을 baseline(단일 안정 연결)으로 낮추면 커널 누적·재부팅 주기를 크게
완화**할 수 있다.

---

## 2. 현재 구조 (master) — churn 발생원

```
[에이전트 N개] 각각:
  aidesk-channel MCP daemon
    ├─ WS  → backend /ws/messages        (분 단위 disconnect/reconnect cycle)
    ├─ fetch poll → backend /api/...     (5초 주기, server.js:670 setInterval)
    └─ helper 연결
  desktop-agent(helper)
    ├─ 30초 reporter POST /api/desktop/local-info
    └─ SSE subscribe /api/desktop/events
  tmux send-keys                          ← idle 에이전트 깨우기(RPA)
backend-py
    ├─ ws_broker (in-memory)   — 단일 replica 제약
    └─ SseBroker (in-memory)   — 단일 replica 제약 (Redis 미사용)
```

churn 유발 요소(에이전트 수에 비례):

| 요소 | 주기 | 비고 |
|---|---|---|
| `pollInbox` fetch | 5초 | `aidesk-channel/src/server.js:670` — 가장 큰 churn원 |
| WS 재연결 | 분 단위 | `ws.py` 주석의 "분 단위 disconnect/reconnect cycle" |
| helper reporter | 30초 | `POST /api/desktop/local-info` |
| SSE 재구독 | 끊길 때마다 | EventSource reconnect |

→ 14일 × N에이전트 × (폴링+재연결+리포터) = 누적 연결 생성·종료가 수백만 건 → TIME_WAIT/pf/NAT 누적.

---

## 3. 목표

연결 churn을 **단일 안정 연결(part4 클라이언트) 수준**으로 낮춰, 커널 네트워크 테이블 누적을
최소화하고 재부팅 주기를 대폭 연장한다. (재부팅 "완전 제거"가 아니라 "주기 연장 + 계획화"가 목표.)

---

## 4. 개선안

### A. 폴링 제거 — WS push 단일화 〔효과 大〕
- `aidesk-channel/src/server.js`의 `setInterval(pollInbox, POLL_MS)`(line 670) **제거**.
- 메시지 도착은 backend의 WS push(`message.deliver`)로만 수신.
- 폴링은 "재연결 직후 백로그 1회 동기화"에만 한정(주기 폴링 금지).
- 부수효과: 무한 증가하던 `seenMessageIds` Set(server.js:74) 의존도 축소 — push 기반이면
  중복 방지 로직을 "최근 N개 ring buffer"로 한정 가능.

### B. 연결 통합 — 머신당 단일 WS multiplex 〔효과 大, 10개+ 환경 필수〕
- 현재: 에이전트마다 WS 1개 → N개 연결 × churn.
- 제안: **desktop-agent(helper) 1개가 backend로 단일 영속 WS**를 유지하고, 받은 이벤트를
  로컬에서 각 에이전트로 fan-out(stdio/IPC).
- 효과: **N개 연결 → 1개**. 재연결 지점도 1곳으로 수렴 → churn 급감.
- 10개+ 환경에서 이 통합이 없으면 아래 다른 개선을 해도 churn이 다시 N배로 늘어남.

### C. 재연결 backoff + keep-alive 〔효과 中〕
- 분 단위 무조건 재연결 → **지수 backoff** 재연결.
- WS ping/pong keep-alive로 연결을 *유지*(끊었다 다시 맺지 않도록).

### D. presence 단순화 — part4식 heartbeat + 연결 레지스트리 〔효과 中, 복잡도 大폭↓〕
- 현재: tmux mtime 추론 + helper 30s reporter + ws-touch + "zombie idle" 엣지케이스 혼재.
- 제안: **WS heartbeat + 연결 레지스트리**(part4의 `WebSocketSessionManager` 패턴, 이미
  `ws_broker`로 절반 이식됨)로 일원화.
- 단, 수신자가 CLI라 "tmux 세션 실제 존재" 확인은 **보조 신호로 유지** 권장(전달 직전 검증).
- 참고: 현재 watcher는 `active→idle` 강등만 하고 `idle→offline` 전이가 없어, helper가 죽으면
  **좀비 idle 영구 잔류**(watcher.py:26~). heartbeat 모델로 가면 이 엣지케이스도 자연 해소.

### E. idle 에이전트 깨우기 — Claude Code Channels로 send-keys 대체 〔검증 필요〕
- 확정: MCP 표준 알림/Hooks/`claude -p`/SDK 스트리밍은 **idle 세션을 못 깨움**. push-to-wake가
  되는 유일한 공식 메커니즘은 **Claude Code "Channels"**.
- 조건: 세션이 *이미 실행 중*이어야 함 → 우리 환경(tmux 상주)은 충족.
- 제약: 리서치 프리뷰(v2.1.80+), Anthropic 인증 필요, 10개+ 동시성 안정성 **별도 검증 필요**.
- 제안: in-house channel(이미 `channel`/`feat/in-house-channel` 브랜치에서 작업 중으로 추정)을
  통해 backend → 실행 중 세션으로 push. **`tmux send-keys`는 fallback으로 유지**.
- 주의: Channels를 에이전트마다 별도 연결로 붙이면 **다시 per-agent churn** → 반드시 B(단일
  helper multiplex)와 함께 설계.

---

## 5. 목표 구조 (요약도)

```
backend-py (단일 replica; 수평확장 시 §6)
    └─ WS /ws/messages  ──(단일 영속 WS, keep-alive)──┐
                                                       │
[desktop-agent / helper] 1개  ◀───────────────────────┘
    ├─ 로컬 fan-out → 각 에이전트(in-house channel push)로 메시지 전달 → 턴 시작
    ├─ presence: WS heartbeat (+ tmux 존재 보조 확인)
    └─ tmux send-keys = Channels 실패 시 fallback
```

핵심: **백엔드와의 네트워크 연결은 머신당 1개의 안정 WS만.** 폴링·per-agent 연결·무조건
재연결 제거.

---

## 6. Redis / 수평 확장 (part4 대비)

- AI-DESK는 **Redis 미사용**. `ws_broker`/`SseBroker` 모두 **프로세스 내 in-memory**.
- 결과: **backend는 현재 단일 replica로만 정상 동작.** replica>1이면 A pod 발신 메시지가
  B pod 구독자에게 전달 안 됨(`sse.py:25` 주석 명시).
- 향후 수평 확장이 필요하면 part4처럼 **Redis pub/sub(또는 동급 외부 broker)** 도입 필요.
- 이는 churn 문제와 별개이나, 통신 구조 리팩터링 시 함께 검토 권장(broker 추상화 지점 확보).

---

## 7. 환원 불가능한 부분 — 유지할 운영 장치

churn을 줄여도 0은 아니므로(잔여 재연결·비정상 종료 소켓), 아래는 **유지**:
- helper `/api/cleanup` (stale daemon kill) + `/api/system/status`
- 대시보드 resource-cleanup 페이지 + 재부팅 권고 배너(uptime>14일 + daemon 3+)
- LocalResourceBar + status_history 24h 차트(모니터링)

목표는 배너의 권고 주기를 14일에서 더 멀리 밀어내는 것.

---

## 8. 영향 받는 코드 (작업 체크리스트)

| 파일 | 변경 |
|---|---|
| `aidesk-channel/src/server.js` | `setInterval(pollInbox)` 제거(A), `seenMessageIds` ring buffer화(A) |
| `desktop-agent/src/aidesk_agent/` | 단일 WS multiplex + 로컬 fan-out(B), backoff 재연결(C), Channels push 연동(E) |
| `backend-py/app/messages/ws.py` | heartbeat 기반 presence 일원화(D), 단일 채널 통합 검토 |
| `backend-py/app/messages/sse.py` | WS와 SSE 중복 시 채널 단일화 검토; broker 추상화(Redis 대비, §6) |
| `backend-py/app/agents/watcher.py` | presence 단순화 후 `active→idle`만 하던 로직 재정의(D) |

---

## 9. 리스크 & 검증

- **Channels**: 리서치 프리뷰 — 10개+ 동시 세션 안정성, API 변경 가능성 검증 필요. fallback(send-keys) 유지.
- **단일 helper WS = SPOF**: helper 죽으면 전체 영향. 이미 0.8.18 watchdog self-ping으로 보완 중 — 단일화 시 watchdog 신뢰성 강화 필수.
- **단일 replica 제약**: §6 — 확장 전까지 backend는 1 replica 유지.
- **검증 방법**: 리팩터 전/후로 §1 측정 — 에이전트 수 고정 후 `lsof`로 TCP/TIME_WAIT 수,
  helper RSS, k8s 백엔드 idle-in-transaction을 24h 추이 비교. churn 지표(시간당 신규 소켓 수)가
  핵심 KPI.

---

## 10. 한 줄 요약

연결 churn이 커널 네트워크 상태를 채워 재부팅을 부른다. **폴링 제거 + 머신당 단일 영속 WS
multiplex + Channels 깨우기 + part4식 heartbeat presence**로 churn을 baseline까지 낮추는 것이
근본 완화책이며, 잔여분은 기존 cleanup/배너로 관리한다. (수평 확장이 필요해지면 Redis 도입은
별도 트랙.)
