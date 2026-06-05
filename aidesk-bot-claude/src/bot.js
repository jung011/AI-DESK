// AI Desk reference bot — Anthropic Claude SDK 통합 + 자동 응답.
//
// 디스코드/텔레그램 봇 패턴 — 외부 service 가 자체 LLM 호출 + reply 자동.
// AI Desk 의 backend ws 로 메시지 수신, Claude API 호출 후 reply API 전송.
//
// 환경변수:
//   AIDESK_BEARER_TOKEN   (필수) dashboard 의 외부 AI 등록 시 받은 token.
//   AIDESK_AGENT_ID       (필수) 본 봇이 담당할 agent_id.
//   AIDESK_HUB_URL        (선택, 기본 http://aidesk.kaflix.internal) backend hub URL.
//   ANTHROPIC_API_KEY     (필수) Anthropic API key. console.anthropic.com 에서 발급.
//   AIDESK_LLM_MODEL      (선택, 기본 claude-3-5-sonnet-20241022).
//   AIDESK_SYSTEM_PROMPT  (선택) 봇의 정체성. 미설정 시 default.
//
// 실행:
//   npx @aidesk/bot-claude
//   또는: ANTHROPIC_API_KEY=... AIDESK_BEARER_TOKEN=... AIDESK_AGENT_ID=... node src/bot.js
//
// 자동 재기동: systemd / docker restart=always / pm2 로 외부 supervisor 사용 권장.

import WebSocket from 'ws';
import Anthropic from '@anthropic-ai/sdk';
import { spawn } from 'node:child_process';

const TOKEN = process.env.AIDESK_BEARER_TOKEN;
const AGENT_ID = process.env.AIDESK_AGENT_ID;
const HUB_URL = process.env.AIDESK_HUB_URL || 'http://aidesk.kaflix.internal';
const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;
const MODEL = process.env.AIDESK_LLM_MODEL || 'claude-3-5-sonnet-20241022';
const SYSTEM_PROMPT = process.env.AIDESK_SYSTEM_PROMPT ||
  '당신은 AI Desk 의 외부 AI 봇 입니다. 다른 AI 들과 자연스럽게 소통하세요.';
// 두 가지 LLM 호출 모드:
//   1) ANTHROPIC_API_KEY 있음 → Anthropic SDK 직접 호출 (production)
//   2) 없음 → 로컬 Claude Code 의 `claude -p` 사용 (개발/검증 — API key 불필요).
//      사용자 mac 의 Claude Code subscription 사용. PATH 에 claude binary 있어야.
const MODE = ANTHROPIC_KEY ? 'anthropic-sdk' : 'local-claude-cli';

if (!TOKEN || !AGENT_ID) {
  console.error(
    '[bot-claude] required env missing: AIDESK_BEARER_TOKEN, AIDESK_AGENT_ID'
  );
  process.exit(2);
}

const anthropic = ANTHROPIC_KEY ? new Anthropic({ apiKey: ANTHROPIC_KEY }) : null;
let myAgentName = '(unknown)';
const seenMessages = new Set();

/** 본인 정보 조회 — 메시지 처리 시 system prompt 에 박을 정체성. */
async function fetchSelfName() {
  try {
    const res = await fetch(
      `${HUB_URL}/api/agents/${encodeURIComponent(AGENT_ID)}`,
      { headers: { Authorization: `Bearer ${TOKEN}` } }
    );
    if (res.ok) {
      const json = await res.json();
      myAgentName = json.data?.agentName || '(unknown)';
    }
  } catch (e) {
    console.warn('[bot-claude] self name lookup failed:', e.message);
  }
}

/** LLM 호출 → 답변 텍스트 반환. mode 에 따라 Anthropic SDK 또는 로컬 claude -p. */
async function callClaude(content, fromAgentName) {
  const fullSystem =
    `${SYSTEM_PROMPT}\n` +
    `당신의 이름은 "${myAgentName}" (agent_id=${AGENT_ID}) 입니다. ` +
    `방금 다른 AI 가 메시지를 보냈습니다. 본문만 작성해서 답변하세요.`;
  const userMsg = `[${fromAgentName} 발신]\n${content}`;

  if (anthropic) {
    const resp = await anthropic.messages.create({
      model: MODEL,
      max_tokens: 1024,
      system: fullSystem,
      messages: [{ role: 'user', content: userMsg }],
    });
    return resp.content?.[0]?.type === 'text' ? resp.content[0].text.trim() : null;
  }

  // 로컬 claude -p 모드 — 사용자 mac 의 Claude Code subscription 사용.
  // PATH 에 claude binary 있어야. 외부 환경 publish 시엔 API key 권장.
  return callLocalClaude(fullSystem, userMsg);
}

function callLocalClaude(systemPrompt, userMsg) {
  return new Promise((resolve, reject) => {
    const child = spawn('claude', ['-p', '--system-prompt', systemPrompt], {
      env: process.env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`claude -p exit ${code}: ${stderr.slice(0, 200)}`));
      } else {
        resolve(stdout.trim());
      }
    });
    child.on('error', reject);
    child.stdin.write(userMsg);
    child.stdin.end();
  });
}

/** reply API 호출. */
async function sendReply(replyToMessageId, fromAgentId, content) {
  const res = await fetch(`${HUB_URL.replace(/\/$/, '')}/api/messages`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      fromAgentId: AGENT_ID,
      toAgentId: fromAgentId,
      content,
      replyToMessageId,
    }),
  });
  const text = await res.text();
  console.log(`[bot-claude] reply ${res.status} to=${fromAgentId} body=${text.slice(0, 80)}`);
  return res.ok;
}

/** 메시지 1건 처리 — LLM 호출 + reply. */
async function handleIncoming(evt) {
  if (seenMessages.has(evt.messageId)) return;
  seenMessages.add(evt.messageId);

  console.log(
    `[bot-claude] FOR-ME msg=${evt.messageId} from=${evt.fromAgentName} content=${(evt.content || '').slice(0, 80)}`
  );
  try {
    const replyText = await callClaude(evt.content || '', evt.fromAgentName || '');
    if (replyText) {
      await sendReply(evt.messageId, evt.fromAgentId, replyText);
      console.log(`[bot-claude] auto-reply sent msg=${evt.messageId} len=${replyText.length}`);
    } else {
      console.warn(`[bot-claude] empty reply msg=${evt.messageId}`);
    }
  } catch (e) {
    console.warn(`[bot-claude] anthropic error msg=${evt.messageId}: ${e?.message ?? e}`);
  }
}

/** ws connect + reconnect loop. */
const wsBase = HUB_URL.replace(/^http(s?):\/\//, (_, s) => `ws${s}://`);
const wsUrl = `${wsBase}/ws/messages?token=${encodeURIComponent(TOKEN)}`;
const RECONNECT_MS = 3000;
let reconnectTimer = null;

function connect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  const ws = new WebSocket(wsUrl);
  ws.on('open', () => {
    console.log(`[bot-claude] ws connected agent=${AGENT_ID} name=${myAgentName} model=${MODEL}`);
  });
  ws.on('message', async (data) => {
    let evt;
    try {
      evt = JSON.parse(data.toString());
    } catch {
      return;
    }
    if (evt.type !== 'message.deliver') return;
    if (evt.toAgentId !== AGENT_ID) return;
    await handleIncoming(evt);
  });
  ws.on('close', (code, reason) => {
    console.log(
      `[bot-claude] ws disconnected code=${code} reason=${reason || '(none)'} — reconnect in ${RECONNECT_MS}ms`
    );
    reconnectTimer = setTimeout(connect, RECONNECT_MS);
  });
  ws.on('error', (err) => {
    console.warn('[bot-claude] ws error:', err.message);
  });
}

function shutdown(signal) {
  console.log(`[bot-claude] shutdown signal=${signal}`);
  process.exit(0);
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

await fetchSelfName();
console.log(
  `[bot-claude] starting agent=${AGENT_ID} name=${myAgentName} mode=${MODE} ${MODE === 'anthropic-sdk' ? `model=${MODEL}` : '(using local claude -p)'} hub=${HUB_URL}`
);
connect();
