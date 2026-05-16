#!/usr/bin/env node
/**
 * AI Desk — Claude Code 가 사용자 응답을 기다리는 상태를 마커 파일로 기록.
 *
 * Claude Code 의 hooks 가 stdin 으로 JSON 페이로드를 흘려보낸다. 페이로드의
 * session_id 와 hook_event_name 을 기준으로:
 *   - mark: ~/.claude/aidesk-prompt/{session_id}.json 작성 → Helper 의 claude_scanner 가
 *     status="waiting" 으로 격상
 *   - clear: 파일 삭제 → status 가 active/idle/done 로 복귀
 *
 * argv[2] = "mark" | "clear"
 * argv[3] = reason (mark 일 때만, 선택)
 *
 * 시그널/exit code 는 항상 0 으로 종료 — 훅 실패가 Claude Code 동작을 멈추면 안 됨.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');

const MARKER_DIR = path.join(os.homedir(), '.claude', 'aidesk-prompt');

function readStdin() {
  try {
    const data = fs.readFileSync(0, 'utf-8');
    return data ? JSON.parse(data) : {};
  } catch (_) {
    return {};
  }
}

function safeMkdir(dir) {
  try { fs.mkdirSync(dir, { recursive: true }); } catch (_) { /* ignore */ }
}

function main() {
  const mode = process.argv[2] || 'mark';
  const reason = process.argv[3] || '';
  const payload = readStdin();
  const sessionId = payload.session_id || payload.sessionId;
  if (!sessionId || typeof sessionId !== 'string') return;

  safeMkdir(MARKER_DIR);
  const file = path.join(MARKER_DIR, `${sessionId}.json`);

  if (mode === 'clear') {
    try { fs.unlinkSync(file); } catch (_) { /* ignore */ }
    return;
  }

  // mark
  const marker = {
    sessionId,
    reason: reason || payload.hook_event_name || 'prompt',
    toolName: payload.tool_name || null,
    cwd: payload.cwd || null,
    markedAt: new Date().toISOString(),
  };
  try {
    fs.writeFileSync(file, JSON.stringify(marker), { encoding: 'utf-8', mode: 0o644 });
  } catch (_) { /* ignore — hook 실패가 사용자 워크플로를 막으면 안 됨 */ }
}

try { main(); } catch (_) { /* never throw */ }
process.exit(0);
