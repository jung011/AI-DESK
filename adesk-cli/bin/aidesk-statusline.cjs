#!/usr/bin/env node
/*
 * AI Desk Claude Code statusline.
 *
 * Claude Code 가 statusLine 설정을 통해 매 프롬프트 갱신마다 이 스크립트를 호출하며
 * stdin 으로 세션 메타데이터(JSON) 를 흘려 보낸다. 그 JSON 에는 /usage 에서 보던
 * `rate_limits.five_hour.used_percentage` 와 `context_window.remaining_percentage`
 * 가 들어있다 — Claude Code 외부에서 이 값을 합법적으로 받을 수 있는 유일한 채널.
 *
 * 동작:
 *   1. stdin 에서 JSON 을 읽는다.
 *   2. 핵심 필드를 ~/.claude/aidesk-usage/{sessionId}.json 에 즉시 기록한다.
 *      (AI Desk 백엔드가 이 디렉토리를 폴링해 실제 /usage 와 같은 값을 보여준다.)
 *   3. 터미널엔 짧은 한 줄을 그려 사용자가 그대로 보던 statusline 자리에 표시한다.
 *
 * 설치:
 *   ~/.claude/settings.json 에 다음 블록을 추가.
 *     "statusLine": {
 *       "type": "command",
 *       "command": "node \"<repo>/adesk-cli/bin/aidesk-statusline.js\""
 *     }
 *   Claude Code 재시작.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const STATE_DIR = path.join(os.homedir(), '.claude', 'aidesk-usage');

const stdinTimeout = setTimeout(() => process.exit(0), 3000);

let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (c) => (buf += c));
process.stdin.on('end', () => {
  clearTimeout(stdinTimeout);
  try {
    const data = JSON.parse(buf);
    persist(data);
    process.stdout.write(renderLine(data));
  } catch {
    // Silent fail — statusline must never crash the prompt.
  }
});

function persist(data) {
  const sessionId = data.session_id || data.sessionId || 'unknown';
  const ctxRem =
    data.context_window?.remaining_percentage ??
    data.context?.remaining_percentage ??
    null;
  const fiveHour = data.rate_limits?.five_hour || null;
  const weekly =
    data.rate_limits?.weekly_all ||
    data.rate_limits?.weekly ||
    null;

  const record = {
    sessionId,
    model: data.model?.display_name || data.model || null,
    cwd: data.workspace?.current_dir || data.cwd || null,
    contextRemainingPct: ctxRem,
    fiveHourUsedPct: fiveHour?.used_percentage ?? null,
    fiveHourResetsAt: fiveHour?.resets_at ?? null,
    weeklyUsedPct: weekly?.used_percentage ?? null,
    weeklyResetsAt: weekly?.resets_at ?? null,
    updatedAt: Date.now(),
  };

  try {
    fs.mkdirSync(STATE_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(STATE_DIR, `${sessionId}.json`),
      JSON.stringify(record),
    );
  } catch {
    // 디스크 IO 실패는 statusline 렌더에 영향 주지 않게 무시.
  }
}

function renderLine(data) {
  const model = data.model?.display_name || 'Claude';
  const dir = data.workspace?.current_dir
    ? path.basename(data.workspace.current_dir)
    : '';

  const ctxRem =
    data.context_window?.remaining_percentage ??
    data.context?.remaining_percentage ??
    null;
  const fiveUsed = data.rate_limits?.five_hour?.used_percentage ?? null;

  let parts = [`\x1b[2m${model}\x1b[0m`];
  if (dir) parts.push(`\x1b[2m${dir}\x1b[0m`);
  if (ctxRem != null) {
    const used = Math.max(0, Math.min(100, Math.round(100 - ctxRem)));
    parts.push(color(used, `ctx ${used}%`));
  }
  if (fiveUsed != null) {
    const used = Math.max(0, Math.min(100, Math.round(fiveUsed)));
    parts.push(color(used, `5h ${used}%`));
  }
  return parts.join(' \x1b[2m·\x1b[0m ');
}

function color(pct, text) {
  let code;
  if (pct < 50) code = '\x1b[38;5;110m';
  else if (pct < 65) code = '\x1b[38;5;108m';
  else if (pct < 80) code = '\x1b[38;5;173m';
  else code = '\x1b[38;5;174m';
  return `${code}${text}\x1b[0m`;
}
