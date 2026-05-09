# aidesk-channel

AI Desk 의 AI 측 last mile MCP 서버. 양쪽 AI 에 stdio MCP 로 등록하면 AI 가 도구 호출로 메시지를 송수신할 수 있다.

## 도구

| 도구 | 용도 |
|---|---|
| `send_to(target_agent, content, reply_to_message_id?)` | 다른 AI 에게 메시지 발신 |
| `reply(message_id, content)` | 받은 `<channel>` 태그의 task_id 로 답변 |
| `check_inbox(unread_only?, limit?)` | 미확인 수신 메시지 조회 |
| `list_agents()` | 다른 AI 목록 조회 |

## 도착 알림

5초마다 inbox 를 폴링해 새 delivered 메시지를 발견하면 stdio 로 `notifications/message` 를 push. 본문 형식 :

```
<channel source="aidesk-channel" task_id="<messageId>" from="<senderName>">
{메시지 본문}
</channel>
```

답변 시에는 `<channel>` 태그의 `task_id` 를 `reply` 도구의 `message_id` 인자에 그대로 넣는다.

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `AIDESK_AGENT_ID` | Y | 이 인스턴스가 어떤 `t_ai_agent` 행에 해당하는지 (UUID) |
| `AIDESK_API_URL`  | N | 백엔드 베이스 URL (기본 `http://localhost:8081`) |
| `AIDESK_POLL_MS`  | N | inbox 폴링 주기 ms (기본 5000) |

## 설치

```bash
npm install        # 이 폴더에서
```

## Claude Code 등록 예시 (`~/.claude.json` 또는 프로젝트 `.claude/settings.json`)

각 AI 인스턴스 마다 별도 server 등록 — `AIDESK_AGENT_ID` 가 다르다 :

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

## 자체 저장소 없음

본 서버는 어떤 데이터도 자체 보관하지 않는다 — 모든 송수신은 AI Desk 백엔드 REST API 에 위임한다. SSOT 는 백엔드 DB.
