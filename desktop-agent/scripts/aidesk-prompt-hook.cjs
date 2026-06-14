#!/usr/bin/env node
/**
 * AI Desk — Claude Code 가 사용자 응답을 기다리는 상태를 마커 파일로 기록.
 *
 * Claude Code 의 hooks 가 stdin 으로 JSON 페이로드를 흘려보낸다. 페이로드의
 * session_id 와 hook_event_name 을 기준으로:
 *   - mark : ~/.claude/aidesk-prompt/{session_id}.json 작성 → Helper 의 claude_scanner 가
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

function writeMarker(sessionId, reason, payload) {
  safeMkdir(MARKER_DIR);
  const file = path.join(MARKER_DIR, `${sessionId}.json`);
  const marker = {
    sessionId,
    reason,
    toolName: payload.tool_name || null,
    cwd: payload.cwd || null,
    notificationMessage: payload.message ? String(payload.message).slice(0, 200) : null,
    markedAt: new Date().toISOString(),
  };
  try {
    fs.writeFileSync(file, JSON.stringify(marker), { encoding: 'utf-8', mode: 0o644 });
  } catch (_) { /* ignore */ }
}

/** Notification 훅은 권한 요청 외에도 ambient idle 알림 등으로 fire 되므로
 *  message 텍스트를 보고 진짜 사용자 액션이 필요한 케이스만 통과시킨다.
 *  주의: "Claude is waiting for your input" 같은 idle 알림은 사용자가 손대야 할 신호가 아니라
 *  단순 60s 무응답 reminder 이므로 제외 — 평문 질문은 Stop 휴리스틱(`?`) 으로 따로 잡힘. */
function isUserActionableNotification(payload) {
  const msg = String(payload.message || '').toLowerCase();
  if (!msg) return false; // message 가 비면 ambient 로 간주 (안전)
  // 권한 / 승인 키워드만 — 영문(claude code 기본) + 한글
  return /permission|approval|approve|authoriz|needs your (consent|approval|permission)|권한|승인/.test(msg);
}

function deleteMarker(sessionId) {
  const file = path.join(MARKER_DIR, `${sessionId}.json`);
  try { fs.unlinkSync(file); } catch (_) { /* ignore */ }
}

function main() {
  const mode = process.argv[2] || 'mark';
  const reason = process.argv[3] || '';
  const payload = readStdin();
  const sessionId = payload.session_id || payload.sessionId;
  if (!sessionId || typeof sessionId !== 'string') return;

  if (mode === 'clear') {
    deleteMarker(sessionId);
    return;
  }

  // mark (기본)
  // Notification 훅은 권한 요청 외에도 ambient idle 알림으로 fire 되므로 필터.
  if (payload.hook_event_name === 'Notification' && !isUserActionableNotification(payload)) {
    return;
  }
  writeMarker(sessionId, reason || payload.hook_event_name || 'prompt', payload);
}

try { main(); } catch (_) { /* never throw */ }
process.exit(0);
