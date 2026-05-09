# adesk-cli

AI Desk 1단계 last mile 응답 회수 도구. tmux 세션 안에서 받은 메시지에 답변할 때 사용한다.

## 설치

이 폴더에서 :

```bash
npm install
npm link        # PATH 에 `adesk` 등록
```

또는 직접 호출 :

```bash
node /Users/jsh/Documents/jsh/workspace/ai-desk/adesk-cli/bin/adesk whoami
```

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `AIDESK_AGENT_ID` | Y | 이 tmux 세션이 어떤 `t_ai_agent` 행에 해당하는지 (UUID) |
| `AIDESK_API_URL`  | N | 백엔드 베이스 URL (기본 `http://localhost:8081`) |
| `AIDESK_API_TOKEN` | N | 향후 인증 도입 시 사용 (현재는 무시) |

`.zshrc` 등에 export 후, tmux 세션 시작 시 자동 상속 :

```bash
export AIDESK_AGENT_ID=a1b2c3d4-0000-0000-0000-000000000001
export AIDESK_API_URL=http://localhost:8081
```

## 명령

### `adesk whoami`

현재 환경변수와 백엔드 인식 결과를 출력. 셋업 검증용.

```
$ adesk whoami
API URL:      http://localhost:8081
Agent ID:     a1b2c3d4-0000-0000-0000-000000000001
...
Agent Name:   코드 리뷰 AI
Tmux Session: aidesk-a1b2c3d4
Status:       active
Workspace:    /workspace/project-alpha
Model:        claude-opus-4-7
Context:      68%
Connectivity: ✓ OK
```

### `adesk reply <messageId> <content>`

받은 메시지에 답변. tmux 입력창에 도착한 헤더 `[aidesk · FROM:.. | MSG:<id>] ...` 의 `<id>` 부분을 그대로 사용한다.

```
$ adesk reply 8c2f5e4a-... "확인했어. 보강 커밋 올렸어."
✓ Replied. status=delivered  id=...
```

옵션 :

- `--stdin` 본문을 STDIN 으로 입력 (multi-line 가능)
  ```
  cat reply.md | adesk reply <id> --stdin
  ```
- `--json`  응답 envelope 을 JSON 으로 출력 (스크립팅 친화)

## 종료 코드

| 코드 | 의미 |
|---|---|
| 0 | 성공 |
| 1 | 일반 오류 (네트워크 / 백엔드 4xx / 원본 메시지 없음 등) |
| 2 | 정책 위반으로 status=failed 또는 envelope.result != 0 |
| 3 | 환경변수 미설정 |
