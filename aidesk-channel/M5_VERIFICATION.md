# M5 검증 가이드 — 다음 세션에서 실행

aidesk-channel MCP 서버는 작성·기동 smoke 까지 통과한 상태. 실제 도구 호출 검증은 Claude Code 가 새 세션에서 mcp 설정을 읽어들일 때만 가능하므로 다음 단계에 진행한다.

## 1. 사전 조건

### 1-1. 백엔드 + DB 가동
```bash
docker ps | grep postgres-db   # postgres-db 컨테이너 살아있어야 함
cd /Users/jsh/Documents/jsh/workspace/ai-desk/backend && ./gradlew bootRun
# Started AiDeskApplication ... port 8081 까지 확인
```

### 1-2. 시드 에이전트 살아있는지 확인
```bash
curl -s http://localhost:8081/api/agents | python3 -m json.tool | head -30
```
3건 (코드 리뷰 AI / 문서화 AI / 테스트 AI) + 환경 변동에 따라 추가될 수 있음.

## 2. mcp.json 등록

`~/.claude.json` 또는 프로젝트 `.claude/settings.json` 의 `mcpServers` 블록에 추가 :

```json
{
  "mcpServers": {
    "aidesk-channel": {
      "command": "node",
      "args": ["/Users/jsh/Documents/jsh/workspace/ai-desk/aidesk-channel/bin/aidesk-channel"],
      "env": {
        "AIDESK_AGENT_ID": "a1b2c3d4-0000-0000-0000-000000000001",
        "AIDESK_API_URL":  "http://localhost:8081"
      }
    }
  }
}
```

> 한 사용자 환경에서 두 AI 인스턴스를 동시에 돌려보려면 두 개의 다른 mcp 항목 (이름·AGENT_ID 다르게) 을 등록한다. 또는 두 별개의 Claude Code 세션이 각각 자기 mcp 설정을 가진다.

## 3. 새 Claude Code 세션 시작

현재 세션은 mcp 설정 로드 시점이 지났으므로 **새 세션을 띄워야** 도구가 노출된다.

```bash
# 새 터미널 또는 새 Claude Code 인스턴스
claude
```

세션이 떠지면 도구 목록에 다음이 보여야 한다 :

- `mcp__aidesk-channel__send_to`
- `mcp__aidesk-channel__reply`
- `mcp__aidesk-channel__check_inbox`
- `mcp__aidesk-channel__list_agents`

## 4. 검증 시나리오

### 4-1. list_agents
다음 도구를 호출해 다른 AI 가 보이는지 확인.
```
mcp__aidesk-channel__list_agents()
```
응답에 자기 자신(코드 리뷰 AI)은 빠지고 문서화 AI / 테스트 AI 가 나와야 한다 (단 done 상태인 테스트 AI는 제외될 수 있음).

### 4-2. check_inbox
미확인 메시지를 점검.
```
mcp__aidesk-channel__check_inbox({ unread_only: true, limit: 10 })
```
이 시점에 inbox 가 비어 있으면 빈 배열.

### 4-3. send_to (다른 AI 에게 발신)
```
mcp__aidesk-channel__send_to({
  target_agent: "문서화 AI",
  content: "MCP 도구 호출 검증입니다."
})
```
응답 : `{ messageId, status: "delivered" 또는 "failed", ... }`. 문서화 AI 의 tmux 세션이 없으면 status=failed (예상된 동작).

### 4-4. reply (도착 알림 → 답변)
다른 AI 인스턴스에서 send_to 로 우리에게 메시지를 보내면, 5초 안에 `<channel ...>` 형식 알림이 우리 세션에 도착해야 한다. 그 task_id 를 그대로 사용해 답변 :
```
mcp__aidesk-channel__reply({
  message_id: "<task_id from <channel> tag>",
  content: "확인했습니다. 답변합니다."
})
```
DB 의 reply_to_message_id 가 원본을 가리키는지 확인.

## 5. 통과 기준 (M5 Definition of Done)

- [ ] 4 도구가 모두 도구 목록에 노출됨
- [ ] list_agents 가 백엔드 실 데이터 반환
- [ ] send_to 호출이 t_ai_message 에 row INSERT (DB 확인)
- [ ] check_inbox 가 inbox 항목 정확히 반환
- [ ] 5초 폴링이 새 inbox 메시지를 `<channel>` 형식으로 push
- [ ] reply 가 부모 reply_to_message_id 매핑 + 부모 status=replied 갱신

위 6 항목이 모두 ✅ 면 M5 달성.

## 6. 디버깅

서버 stderr 로그는 stdio 세션 stderr 에서 확인.
- mcp 클라이언트(Claude Code) 가 stderr 를 어디로 라우팅하는지에 따라 다름. 보통 `~/.claude/logs/` 또는 ide 콘솔.
- 단독 실행해 stderr 확인이 가능 :
  ```bash
  AIDESK_AGENT_ID=a1b2c3d4-0000-0000-0000-000000000001 \
  AIDESK_API_URL=http://localhost:8081 \
  node /Users/jsh/Documents/jsh/workspace/ai-desk/aidesk-channel/bin/aidesk-channel < /dev/null
  # ctrl-c
  ```

## 7. 흔한 함정

- **AGENT_ID 미설정** → 서버가 즉시 종료 (`AIDESK_AGENT_ID is not set`)
- **백엔드 미가동** → 모든 도구가 `Connection refused` 류 에러
- **AIDESK_AGENT_ID 가 t_ai_agent 에 없는 UUID** → list_agents 등은 동작하지만 send_to 시 백엔드가 404 응답
- **tmux 세션 부재** → send_to 후 status=failed (정상 — last mile 정책)
- **5초 폴링 지연** → push 가 즉시 안 보일 수 있음. AIDESK_POLL_MS 줄여 (e.g. 2000) 디버그 가능
