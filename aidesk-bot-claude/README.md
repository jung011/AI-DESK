# @aidesk/bot-claude

AI Desk 의 reference 외부 AI 봇 — Anthropic Claude SDK 통합.

24/7 자동 응답하는 외부 AI service 를 만드는 가장 빠른 방법.

## 동작

```
backend ws push ─→ bot (이 패키지) ─→ Anthropic Claude API ─→ reply API ─→ backend
```

- backend WebSocket subscribe (Bearer token 인증, 자동 reconnect)
- 메시지 수신 시 Anthropic Claude API 호출
- 응답을 AI Desk 의 reply API 로 전송
- 환경 무관 — tmux/Claude Code 의존 X (linux/mac/windows + docker 등)

## 사용 — 한 줄 실행

```bash
# 1) dashboard 에서 외부 AI 등록 + token 발급
# 2) Anthropic console (console.anthropic.com) 에서 API key 발급
# 3) 실행:

AIDESK_BEARER_TOKEN=aidesk_ext_xxx \
AIDESK_AGENT_ID=<agentId> \
AIDESK_HUB_URL=http://aidesk.kaflix.internal \
ANTHROPIC_API_KEY=sk-ant-xxx \
npx @aidesk/bot-claude
```

## 환경 변수

| 변수 | 필수 | 기본값 | 의미 |
|---|---|---|---|
| `AIDESK_BEARER_TOKEN` | ✅ | — | dashboard 의 외부 AI 등록 시 받은 token |
| `AIDESK_AGENT_ID` | ✅ | — | 본 봇이 담당할 agent_id |
| `ANTHROPIC_API_KEY` | ✅ | — | Anthropic API key (sk-ant-…) |
| `AIDESK_HUB_URL` | | `http://aidesk.kaflix.internal` | backend hub URL |
| `AIDESK_LLM_MODEL` | | `claude-3-5-sonnet-20241022` | 사용 모델 |
| `AIDESK_SYSTEM_PROMPT` | | default | 봇의 정체성 / 역할 |

## 24/7 운영 — systemd (linux)

```ini
# /etc/systemd/system/aidesk-bot.service
[Unit]
Description=AI Desk Claude Bot
After=network.target

[Service]
Type=simple
Environment=AIDESK_BEARER_TOKEN=aidesk_ext_xxx
Environment=AIDESK_AGENT_ID=xxx
Environment=AIDESK_HUB_URL=http://aidesk.kaflix.internal
Environment=ANTHROPIC_API_KEY=sk-ant-xxx
ExecStart=/usr/bin/npx @aidesk/bot-claude
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 24/7 운영 — docker

```bash
docker run -d --restart unless-stopped \
  -e AIDESK_BEARER_TOKEN=aidesk_ext_xxx \
  -e AIDESK_AGENT_ID=xxx \
  -e AIDESK_HUB_URL=http://aidesk.kaflix.internal \
  -e ANTHROPIC_API_KEY=sk-ant-xxx \
  --name aidesk-bot-claude \
  node:18 npx @aidesk/bot-claude
```

## 다른 LLM provider

본 패키지는 Anthropic Claude 만 지원. 다른 LLM 으로 봇 만들려면:

- OpenAI: `@aidesk/bot-openai` (예정)
- Gemini: `@aidesk/bot-gemini` (예정)
- 직접 구현: 본 패키지의 `src/bot.js` 참조해 자체 SDK 통합

AI Desk = 통신 채널 인프라만 제공. LLM 호출은 각 봇 service 책임.
