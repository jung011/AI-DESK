// AI Desk MCP server.
//
// 환경변수:
//   AIDESK_AGENT_ID       선택. 이 MCP 인스턴스가 어느 t_ai_agent 에 해당하는지를 명시.
//                         비어있거나 DB 에 없는 ID 면 process.cwd() 로 자동 매칭.
//   AIDESK_API_URL        선택 (기본 http://localhost:30081).
//   AIDESK_BEARER_TOKEN   선택. 외부 AI service (helper 없는 환경) 에서 사용.
//                         값이 있으면 모든 backend 호출에 Authorization: Bearer 헤더 동봉.
//                         있을 땐 ensureAgentId 가 ENV_AGENT_ID 를 무조건 신뢰
//                         (DB 조회 path 가 토큰 기반이라 본인 row 만 보임).
//   ANTHROPIC_API_KEY     선택. Phase 2 자동 응답 모드. 메시지 수신 시 Claude SDK 직접 호출 →
//                         자동 reply. Claude Code 의 sampling 미지원 우회.
//   AIDESK_LLM_MODEL      선택 (기본 claude-3-5-sonnet-20241022). ANTHROPIC_API_KEY 와 같이.
//
// 4 도구:
//   send_to       다른 AI 에게 메시지 발신
//   reply         받은 메시지에 답변 (replyToMessageId 자동 매핑)
//   check_inbox   미확인 수신 메시지 조회
//   list_agents   다른 AI 목록 조회
//
// 도착 알림:
//   5초마다 inbox 를 폴링해 새 delivered 메시지를 발견하면 stdio 로
//   notifications/message 를 push. 메시지 본문은 다음 형식:
//
//     <channel source="aidesk-channel" task_id="<messageId>" from="<senderName>">
//     {본문}
//     </channel>

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import WebSocket from 'ws';
import fs from 'node:fs';
import path from 'node:path';
import Anthropic from '@anthropic-ai/sdk';

// Phase 2 — mcp 의 stderr 가 Claude Code 의 unix socket 으로 pipe 돼서 별도 진단 어려움.
// per-agent debug log file 로 직접 append — 사용자가 cat 으로 즉시 확인 가능.
const DBG_LOG_DIR = path.join(process.env.HOME || '/tmp', '.aidesk-channel-logs');
try { fs.mkdirSync(DBG_LOG_DIR, { recursive: true }); } catch {}
const DBG_LOG_PATH = path.join(DBG_LOG_DIR, `aidesk-channel-${process.pid}.log`);
function dbg(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  try { fs.appendFileSync(DBG_LOG_PATH, line); } catch {}
  try { process.stderr.write(line); } catch {}
}
dbg(`module loaded — pid=${process.pid} cwd=${process.cwd()} bearer=${!!process.env.AIDESK_BEARER_TOKEN}`);

const ENV_AGENT_ID = process.env.AIDESK_AGENT_ID;
// API_URL 은 env 가 1차 — 단, claude TUI 가 *오랜 시간 도는 동안 사용자가 backend URL
// 을 바꾸면* spawn 시점 env 가 stale 이 된다. 이를 자동 회복하기 위해 같은 mac 의
// helper 에 *최신 backend URL* 을 묻는 보조 경로를 둔다.
let API_URL  = process.env.AIDESK_API_URL || 'http://localhost:30081';
const HELPER_URL = process.env.AIDESK_HELPER_URL || 'http://localhost:30083';
// Phase 2 — 외부 AI service (helper 없는 환경). 있으면 모든 backend 호출에 Bearer.
const BEARER_TOKEN = process.env.AIDESK_BEARER_TOKEN;
// Phase 2 자동 응답 — Anthropic Claude SDK 직접 호출. Claude Code 의 sampling 미지원 우회.
// key 없으면 sampling fallback 시도 (대부분 Method not found 로 실패) → 사용자 trigger 모드.
const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
const ANTHROPIC_MODEL = process.env.AIDESK_LLM_MODEL || 'claude-3-5-sonnet-20241022';
const anthropic = ANTHROPIC_API_KEY ? new Anthropic({ apiKey: ANTHROPIC_API_KEY }) : null;

// 부팅 시 한 번 결정되며, 결정 실패해도 종료하지 않는다 (백엔드 미기동 시점에 claude 가
// MCP 를 띄우는 경우 대비). 도구 호출 시점에 다시 시도한다.
let AGENT_ID = null;
let MY_AGENT_NAME = null;  // Phase 2 — identity 주입용. ensureAgentId 후 채워짐.

// Phase 2 — ws push 받은 메시지 중복 처리 차단. polling 의 seen 과 공유.
const seenMessageIds = new Set();

// ---------------------------------------------------------------------
// 도구 정의
// ---------------------------------------------------------------------

const TOOLS = [
  {
    name: 'send_to',
    description:
      '다른 AI 에이전트에게 메시지를 보냅니다. target_agent 는 에이전트 이름 또는 UUID.',
    inputSchema: {
      type: 'object',
      properties: {
        target_agent: { type: 'string', description: '받는 AI 의 이름 또는 UUID' },
        content: { type: 'string', description: '메시지 본문 (최대 1000자)' },
        reply_to_message_id: {
          type: 'string',
          description: '답장 체인 — 원본 메시지 UUID (선택)'
        }
      },
      required: ['target_agent', 'content']
    }
  },
  {
    name: 'reply',
    description:
      '받은 메시지에 답변합니다. message_id 는 도착 알림(<channel> 태그)의 task_id 를 그대로 전달.',
    inputSchema: {
      type: 'object',
      properties: {
        message_id: { type: 'string', description: '원본 메시지 UUID' },
        content: { type: 'string', description: '답변 본문' }
      },
      required: ['message_id', 'content']
    }
  },
  {
    name: 'check_inbox',
    description: '받은 메시지 목록 조회. 답변 못 한 메시지를 점검할 때 사용.',
    inputSchema: {
      type: 'object',
      properties: {
        unread_only: { type: 'boolean', description: '기본 true' },
        limit: { type: 'number', description: '기본 10' }
      }
    }
  },
  {
    name: 'list_agents',
    description: '다른 AI 에이전트 목록을 조회합니다 (자기 자신만 제외, 상태 무관).',
    inputSchema: { type: 'object', properties: {} }
  }
];

// ---------------------------------------------------------------------
// 백엔드 호출 헬퍼
// ---------------------------------------------------------------------

/**
 * 같은 mac 의 helper 에게 *현재 backend URL* 을 물어 API_URL 갱신.
 * 호출자가 await 하든 안 하든 부수효과로 모듈 내 API_URL 만 업데이트.
 *
 * helper proxy 모드 (AIDESK_API_URL=http://127.0.0.1:PORT/api/proxy) 에선 helper override
 * 차단 — proxy URL 을 backend 직접 URL 로 덮어쓰면 외부 IP socket 격리가 무효화.
 * [[feedback-mcp-bun-external-connect-block]]
 */
async function refreshApiUrlFromHelper() {
  // Bearer token 모드 (외부 service) 는 helper 없는 환경이라 호출 무의미.
  if (BEARER_TOKEN) return;
  // helper proxy 경유 = override 차단. mcp daemon 은 localhost 만 connect 해야 함.
  if (API_URL.includes('/api/proxy')) return;
  try {
    const r = await fetch(`${HELPER_URL}/api/local-info`, {
      signal: AbortSignal.timeout(2000)
    });
    if (!r.ok) return;
    const data = await r.json();
    const fresh = data?.currentBackendUrl;
    if (fresh && fresh !== API_URL) {
      dbg(`aidesk-channel: API_URL ${API_URL} -> ${fresh} (helper override)`);
      API_URL = fresh;
    }
  } catch {
    // helper 미응답이면 기존 API_URL 그대로 유지 — 다음 도구 호출 때 다시 시도.
  }
}

async function api(path, init = {}) {
  const headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
  if (BEARER_TOKEN && !headers.Authorization) {
    headers.Authorization = `Bearer ${BEARER_TOKEN}`;
  }
  let lastErr;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(`${API_URL}${path}`, { ...init, headers });
      const env = await res.json();
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${env?.message || res.statusText}`);
      if (env.result !== 0 && !env.data) throw new Error(env.message || 'backend error');
      return env;
    } catch (e) {
      lastErr = e;
      // 네트워크 / 연결 오류 ('fetch failed' 등) 만 재시도 — HTTP 5xx 같은 응답은 그대로.
      const msg = String(e?.message || '');
      const isNetwork = /fetch failed|ECONNREFUSED|ENOTFOUND|ETIMEDOUT|network|aborted/i.test(msg);
      if (attempt === 0 && isNetwork) {
        await refreshApiUrlFromHelper();
        continue;
      }
      throw e;
    }
  }
  throw lastErr;
}

const isUuid = (s) => typeof s === 'string' && /^[0-9a-f-]{36}$/i.test(s);

/**
 * 우리(이 MCP 인스턴스) 가 어느 t_ai_agent 인지 결정.
 *
 *   1) AIDESK_AGENT_ID env 가 DB 에 살아있는 ID 면 그걸 사용
 *   2) env 가 없거나 DB 에 없으면 process.cwd() 와 t_ai_agent.workspace_dir 매칭
 *   3) 둘 다 실패하면 throw — claude 도구 호출이 명확한 에러 메시지로 떨어짐
 *
 * 결과는 한 번만 캐시. listAgents/sendTo/checkInbox 모두 이 값을 쓴다.
 */
async function ensureAgentId() {
  if (AGENT_ID) return AGENT_ID;

  // Phase 2 — Bearer token 모드 (외부 service). ENV_AGENT_ID 가 필수.
  // backend 가 token 으로 사용자 컨텍스트 결정하므로 cwd 매칭 path 는 의미 없음.
  if (BEARER_TOKEN) {
    if (!ENV_AGENT_ID) {
      throw new Error(
        'aidesk-channel: AIDESK_BEARER_TOKEN 사용 시 AIDESK_AGENT_ID 필수. dashboard 의 외부 AI 등록 응답에서 받은 agentId 를 환경변수로 설정하세요.'
      );
    }
    AGENT_ID = ENV_AGENT_ID;
    // 본인 이름 backend lookup — Bearer 인증으로 본인 row 만 조회 가능.
    try {
      const env = await api(`/api/agents/${encodeURIComponent(ENV_AGENT_ID)}`);
      MY_AGENT_NAME = env.data?.agentName || null;
    } catch (e) {
      dbg(`aidesk-channel: name lookup failed: ${e?.message ?? e}`);
    }
    return AGENT_ID;
  }

  const env = await api('/api/agents');
  const list = env.data?.list || [];

  if (ENV_AGENT_ID) {
    const byEnv = list.find((a) => a.agentId === ENV_AGENT_ID);
    if (byEnv) {
      AGENT_ID = byEnv.agentId;
      MY_AGENT_NAME = byEnv.agentName || null;
      return AGENT_ID;
    }
    dbg(`aidesk-channel: AIDESK_AGENT_ID=${ENV_AGENT_ID} not in DB; falling back to cwd match`);
  }

  const cwd = process.cwd();
  // 정확 일치 우선, 부족하면 prefix 일치 (예: cwd 가 워크스페이스의 하위 폴더에서 떴을 때).
  // 휴먼 entity (workspace_dir='') 제외 — 빈 string + '/' = '/' 이라 모든 cwd 가 prefix
  // 매칭돼 *모든 cwd 의 mcp 가 휴먼 명의로 동작* 하는 버그 차단.
  const exact = list.find((a) => a.workspaceDir === cwd);
  const prefix = exact || list.find((a) => {
    if (!a.workspaceDir) return false;
    return cwd.startsWith(a.workspaceDir + '/');
  });
  if (!prefix) {
    throw new Error(
      `aidesk-channel: no agent matches cwd "${cwd}". 대시보드에서 AI 를 먼저 생성하세요.`
    );
  }
  AGENT_ID = prefix.agentId;
  MY_AGENT_NAME = prefix.agentName || null;
  return AGENT_ID;
}

async function listAgents() {
  const me = await ensureAgentId();
  // callerAgentId 동봉 — backend 가 caller 의 channel 기준으로 reachable 한 AI 만 반환.
  const env = await api(`/api/agents?callerAgentId=${encodeURIComponent(me)}`);
  const others = (env.data?.list || []).filter((a) => a.agentId !== me);
  // self info 항상 동봉 — Claude 가 자기 정체성을 매 호출 시 재확인 (휴먼/내부 AI 혼동 방지).
  return {
    self: { agentId: me, agentName: MY_AGENT_NAME || '(이름 미상)' },
    others,
  };
}

async function resolveAgentId(target) {
  if (isUuid(target)) return target;
  const all = await api('/api/agents');
  const match = (all.data?.list || []).find((a) => a.agentName === target);
  if (!match) throw new Error(`Agent not found: ${target}`);
  return match.agentId;
}

async function sendTo({ target_agent, content, reply_to_message_id }) {
  if (!target_agent || !content) {
    throw new Error('target_agent and content are required');
  }
  const me = await ensureAgentId();
  const toAgentId = await resolveAgentId(target_agent);

  // [송신 전] recipient status 확인 — offline/error 면 silence 가능성 warning,
  // compacting 이면 응답 지연 안내. backend retry-on-reconnect 부재로 (status=sent 무한 대기)
  // 발생하는 무응답 silence 또는 압축 중 자연 지연을 caller LLM 이 즉시 인지하게.
  let preWarning = null;
  try {
    const probe = await api(`/api/agents/${encodeURIComponent(toAgentId)}`);
    const s = probe.data?.status;
    const name = probe.data?.agentName || target_agent;
    if (s === 'offline' || s === 'error') {
      preWarning = `recipient(${name}) status=${s} — 미전달 가능성 높음. retry-on-reconnect 없어 recipient 활성화돼도 자동 catchup 안 됨.`;
    } else if (s === 'compacting') {
      preWarning = `recipient(${name}) 컨텍스트 압축 중 — 응답 1-3분 지연 가능. 메시지는 큐 처리되어 압축 후 자동 도달.`;
    }
  } catch {
    // status fetch 실패는 무시 (송신 자체 진행)
  }

  const body = { fromAgentId: me, toAgentId, content };
  if (reply_to_message_id) body.replyToMessageId = reply_to_message_id;
  const env = await api('/api/messages', { method: 'POST', body: JSON.stringify(body) });
  const message = env.data;

  // [송신 후] backend 는 INSERT 직후 status='sent' 리턴 + virtual thread 로 helper SSE 비동기 push.
  // 정상 흐름이면 1-2초 안에 status='delivered'/'replied' + deliveredAt 채워짐.
  // false-positive warning 회피 위해 'sent' 일 땐 1.5s 후 단건 재조회 후 판단.
  let finalStatus = message?.status;
  let deliveredAt = message?.deliveredAt;
  let errorReason = message?.errorReason;
  if (finalStatus === 'sent' && message?.messageId) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      const check = await api(`/api/messages/${encodeURIComponent(message.messageId)}`);
      const after = check.data;
      if (after) {
        finalStatus = after.status ?? finalStatus;
        deliveredAt = after.deliveredAt ?? deliveredAt;
        errorReason = after.errorReason ?? errorReason;
      }
    } catch {
      // 재조회 실패는 무시 — original status 그대로
    }
  }

  let postWarning = null;
  if (finalStatus === 'sent' && !deliveredAt) {
    postWarning = '1.5s 후에도 status=sent + deliveredAt null — recipient 도달 미확인. last-mile 실패 가능성. 사용자 확인 필요.';
  } else if (finalStatus === 'failed') {
    postWarning = `status=failed${errorReason ? ' — ' + errorReason : ''}`;
  }

  const result = { ...message, status: finalStatus, deliveredAt, errorReason };
  if (preWarning || postWarning) {
    result._warning = [preWarning, postWarning].filter(Boolean).join(' / ');
  }
  return result;
}

async function replyToMessage({ message_id, content }) {
  if (!message_id || !content) throw new Error('message_id and content are required');
  const me = await ensureAgentId();
  const env = await api(`/api/messages/${encodeURIComponent(message_id)}`);
  const orig = env.data;
  if (!orig) throw new Error(`Original message not found: ${message_id}`);
  if (orig.toAgentId !== me) {
    throw new Error('You are not the receiver of this message.');
  }
  return await sendTo({
    target_agent: orig.fromAgentId,
    content,
    reply_to_message_id: message_id
  });
}

async function checkInbox({ unread_only = true, limit = 10 } = {}) {
  const me = await ensureAgentId();
  const url = `/api/messages?agentId=${encodeURIComponent(me)}&direction=inbox&limit=${encodeURIComponent(
    limit
  )}`;
  const env = await api(url);
  let list = env.data?.list || [];
  if (unread_only) {
    list = list.filter(
      (m) => !m.readAt && (m.status === 'delivered' || m.status === 'replied')
    );
  }
  return list;
}

// ---------------------------------------------------------------------
// MCP 서버 + 도구 디스패치
// ---------------------------------------------------------------------

const server = new Server(
  { name: 'aidesk-channel', version: '0.1.0' },
  {
    // Phase 2 — claude/channel = Claude Code 의 자체 push notification 확장.
    // 정확한 path = experimental.claude/channel (binary 의 reference example 발견).
    // 없으면 "Channel notifications skipped: server did not declare claude/channel capability".
    capabilities: {
      tools: {},
      logging: {},
      experimental: { 'claude/channel': {} },
    },
    instructions:
      '이 서버는 AI Desk 의 AI 협업 채널 어댑터입니다. ' +
      '\n\n[정체성] 당신은 AI Desk 에 등록된 *AI 에이전트* 입니다 (휴먼 / 사용자 본인이 아닙니다). ' +
      'list_agents 호출 결과의 self 필드에서 본인의 agent_name 과 agent_id 를 확인할 수 있고, ' +
      '다른 AI 가 채팅에서 부르는 이름이 곧 당신의 이름입니다.' +
      '\n\n[도구] 다른 AI 에게 메시지 → send_to. 받은 메시지(<channel> 태그)에 답 → reply. ' +
      '미확인 점검 → check_inbox. 다른 AI 목록 → list_agents. ' +
      '답변 시 <channel> 태그의 task_id 를 message_id 로 그대로 전달하세요.'
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  try {
    let result;
    switch (name) {
      case 'send_to':     result = await sendTo(args); break;
      case 'reply':       result = await replyToMessage(args); break;
      case 'check_inbox': result = await checkInbox(args); break;
      case 'list_agents': result = await listAgents(); break;
      default: throw new Error(`Unknown tool: ${name}`);
    }
    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }]
    };
  } catch (err) {
    return {
      content: [{ type: 'text', text: `Error: ${err?.message ?? err}` }],
      isError: true
    };
  }
});

// ---------------------------------------------------------------------
// inbox 폴링 + 알림 push
// ---------------------------------------------------------------------

let firstPoll = true;

async function pollInbox() {
  try {
    const list = await checkInbox({ unread_only: true, limit: 20 });
    if (firstPoll) {
      list.forEach((m) => seenMessageIds.add(m.messageId));
      firstPoll = false;
      return;
    }
    for (const m of list) {
      if (seenMessageIds.has(m.messageId)) continue;
      seenMessageIds.add(m.messageId);
      await deliverIncoming({
        messageId: m.messageId,
        fromAgentName: m.fromAgentName,
        content: m.content,
      });
    }
  } catch (err) {
    dbg(`aidesk-channel: poll error: ${err?.message ?? err}`);
  }
}

/**
 * 수신 메시지 한 건 처리 — Phase 2 의 핵심 인터럽트.
 *  1) sampling/createMessage 로 client(외부 AI) 의 자체 LLM 에 응답 요청
 *  2) 받은 응답을 backend reply API 로 자동 전송
 *  3) sampling 지원 안 하는 client 면 sendLoggingMessage 로 표시만 (사람 trigger 모드)
 *
 * sampling 의 client 지원은 initialize handshake 의 capabilities.sampling. 지원하지 않으면
 * SDK 가 createMessage 시 즉시 throw — catch 후 fallback.
 */
async function deliverIncoming({ messageId, fromAgentName, content }) {
  const channelTag =
    `<channel source="aidesk-channel" task_id="${messageId}" from="${fromAgentName}">\n` +
    `${content}\n` +
    `</channel>`;

  // ★ claude code 의 channel notification — session 안 직접 inject (자동 trigger).
  // claude.exe binary 의 example: method='notifications/claude/channel', params.content +
  // params.meta. meta keys 가 [channel] tag attributes 가 됨.
  // 사용자가 `claude --channels server:aidesk-channel-ext --dangerously-load-development-channels server:aidesk-channel-ext`
  // 로 실행해야 활성.
  try {
    await server.notification({
      method: 'notifications/claude/channel',
      params: {
        content: content,
        meta: {
          task_id: messageId,
          sender: fromAgentName,
          source: 'aidesk-channel',
        },
      },
    });
    dbg(`channel notification sent msg=${messageId}`);
  } catch (e) {
    dbg(`channel notification failed: ${e?.message ?? e}`);
  }

  // 사람 모드 fallback / audit — 항상 보내서 로그/UI 에 노출. sampling 자동 응답 환경에서도 audit 용.
  try {
    await server.sendLoggingMessage({
      level: 'info',
      logger: 'aidesk-channel',
      data: channelTag,
    });
  } catch (e) {
    dbg(`aidesk-channel: notify failed: ${e?.message ?? e}`);
  }

  // 1) Anthropic SDK 직접 호출 (Phase 2 옵션 B) — ANTHROPIC_API_KEY 가 있으면 우선.
  //    Claude Code 의 sampling 미지원 우회. 24/7 자동 응답 보장.
  if (anthropic) {
    try {
      dbg(`anthropic call msg=${messageId} model=${ANTHROPIC_MODEL}`);
      const resp = await anthropic.messages.create({
        model: ANTHROPIC_MODEL,
        max_tokens: 1024,
        system:
          `당신은 AI Desk 의 ${MY_AGENT_NAME || 'external AI'} (agent_id=${AGENT_ID}) 입니다. ` +
          `방금 다른 AI 가 메시지를 보냈습니다. 그 메시지에 답변하세요. ` +
          `답변은 본문만 작성하세요 — mcp tool 호출 X.`,
        messages: [
          { role: 'user', content: `[${fromAgentName} 발신]\n${content}` },
        ],
      });
      const replyText = resp?.content?.[0]?.type === 'text'
        ? resp.content[0].text.trim()
        : null;
      if (replyText) {
        try {
          await replyToMessage({ message_id: messageId, content: replyText });
          dbg(`anthropic auto-reply sent msg=${messageId} len=${replyText.length}`);
        } catch (e) {
          dbg(`anthropic auto-reply API failed msg=${messageId}: ${e?.message ?? e}`);
        }
      } else {
        dbg(`anthropic empty reply msg=${messageId}`);
      }
      return;  // 성공/실패 무관 — sampling fallback 시도 안 함.
    } catch (e) {
      dbg(`anthropic SDK error: ${e?.message ?? e}`);
      // SDK 실패 시 fallback 으로 sampling 시도 (대개 Method not found 라 효과 없음).
    }
  }

  // 2) sampling/createMessage fallback — Claude Code 의 sampling 지원 환경 (이론).
  try {
    const result = await server.createMessage({
      systemPrompt:
        `당신은 AI Desk 의 ${MY_AGENT_NAME || 'external AI'} (agent_id=${AGENT_ID}) 입니다. ` +
        `방금 다른 AI 가 메시지를 보냈습니다. 그 메시지에 답변하세요. ` +
        `답변은 reply 형식 — 그대로 본문만 작성하면 됩니다 (mcp tool 호출 X).`,
      messages: [
        {
          role: 'user',
          content: { type: 'text', text: `[${fromAgentName} 발신]\n${content}` },
        },
      ],
      maxTokens: 1024,
      includeContext: 'none',
    });
    const replyText =
      result?.content?.type === 'text' && typeof result.content.text === 'string'
        ? result.content.text.trim()
        : null;
    if (replyText) {
      // 직접 reply API 호출 — backend 가 채널 정책 + delivered 마킹 자동.
      try {
        await replyToMessage({ message_id: messageId, content: replyText });
        dbg(`aidesk-channel: sampling auto-reply sent for msg=${messageId}`);
      } catch (e) {
        dbg(`aidesk-channel: sampling auto-reply API failed msg=${messageId}: ${e?.message ?? e}`);
      }
    }
  } catch (e) {
    // 가장 흔한 케이스 — client 가 sampling 지원 안 함. 그 땐 silent fallback (logging 만 됨).
    dbg(`aidesk-channel: sampling skipped (client capability missing or refused): ${e?.message ?? e}`);
  }
}

/**
 * Phase 2 — backend ws subscribe. status 토글 (connect=idle / disconnect=offline) 동시에
 * 메시지 푸시 받아 deliverIncoming 호출. polling 은 ws 가 끊긴 동안의 백업으로 유지.
 */
function startWsSubscribe() {
  dbg(`startWsSubscribe called — agent_id=${AGENT_ID}`);
  if (!AGENT_ID) {
    dbg('aidesk-channel: ws subscribe skipped — agent_id not resolved yet');
    return;
  }
  const wsBase = API_URL.replace(/^http(s?):\/\//, (_, s) => `ws${s}://`);
  const wsUrl = BEARER_TOKEN
    ? `${wsBase}/ws/messages?token=${encodeURIComponent(BEARER_TOKEN)}`
    : `${wsBase}/ws/messages?agentId=${encodeURIComponent(AGENT_ID)}`;

  // 지수 backoff — connect fail / disconnect 마다 *두 배씩* 늘려 backend storm 차단.
  // 1s → 2 → 4 → 8 → 16 → 30 (max). connect 성공 시 1s 로 reset.
  // 첫 시도는 즉시 (initial connect 외부 호출).
  const RECONNECT_MIN_MS = 1000;
  const RECONNECT_MAX_MS = 30000;
  let reconnectDelay = RECONNECT_MIN_MS;

  // ping/pong keep-alive — backend 가 *반응 안 함* (network mute / proxy timeout) 사고 시
  // ws.on('close') 가 *바로 못 오는* 케이스 차단. 30s 마다 ping 발사 + 60s 안 pong
  // 안 오면 강제 close → reconnect.
  const PING_INTERVAL_MS = 30000;
  const PONG_TIMEOUT_MS = 60000;

  // 401 (token rotate/revoke/delete) 같은 *명시적 인증 거부* 면 *자가 종료*.
  // 옛 token 박힌 daemon 의 무한 reconnect storm 방지 — backend log 도배 + 사용자 mac CPU 낭비
  // 차단. 사용자는 새 setup script 만 다시 실행하면 됨.
  //
  // 종료 trigger:
  //   - ws.on('close') code=1008 (backend 의 WS_1008_POLICY_VIOLATION — _authenticate reject)
  //   - ws.on('error') 의 메시지 안 'Unexpected server response: 401' (npm ws 의 handshake 401)
  let ws = null;
  let reconnectTimer = null;
  let pingTimer = null;
  let pongDeadlineTimer = null;
  let lastErrorMsg = '';

  function clearKeepAliveTimers() {
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    if (pongDeadlineTimer) { clearTimeout(pongDeadlineTimer); pongDeadlineTimer = null; }
  }

  function exitOnAuthReject(reason) {
    dbg(`aidesk-channel: auth reject — exiting daemon. reason=${reason}`);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    clearKeepAliveTimers();
    // claude code mcp client 에 stderr 로 알림 (사용자가 새 setup 진행 필요).
    process.stderr.write(`[aidesk-channel] auth rejected (${reason}) — daemon exiting. Run new setup script.\n`);
    process.exit(1);
  }

  // backlog 1회 pull — ws 가 *down 동안* 들어온 메시지 흡수. 첫 connect 시점은
  // initial polling 이 이미 마킹했고, *reconnect 후* 가 진짜 backlog 필요 시점.
  // firstWsOpen=true 면 *이미 marker* 했으니 skip. 아니면 pollInbox() 1회.
  let firstWsOpen = true;
  async function pullBacklogOnce() {
    if (firstWsOpen) {
      firstWsOpen = false;
      return;
    }
    dbg('ws reconnected → backlog 1-shot pull');
    await pollInbox();
  }

  function connect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    ws = new WebSocket(wsUrl);
    ws.on('open', () => {
      dbg(`ws connected url=${wsUrl}`);
      lastErrorMsg = '';
      reconnectDelay = RECONNECT_MIN_MS;  // reset backoff

      // ping/pong keep-alive 시작
      clearKeepAliveTimers();
      pingTimer = setInterval(() => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        try {
          ws.ping();
          // pong 안 오면 강제 close 후 reconnect cycle.
          if (pongDeadlineTimer) clearTimeout(pongDeadlineTimer);
          pongDeadlineTimer = setTimeout(() => {
            dbg('aidesk-channel: pong timeout — forcing close');
            try { ws.terminate(); } catch { /* ignore */ }
          }, PONG_TIMEOUT_MS);
        } catch (e) {
          dbg(`aidesk-channel: ping send failed: ${e?.message ?? e}`);
        }
      }, PING_INTERVAL_MS);

      // backlog 흡수 (reconnect 시만).
      pullBacklogOnce().catch((e) => dbg(`aidesk-channel: backlog pull failed: ${e?.message ?? e}`));
    });
    ws.on('pong', () => {
      if (pongDeadlineTimer) {
        clearTimeout(pongDeadlineTimer);
        pongDeadlineTimer = null;
      }
    });
    ws.on('message', async (data) => {
      let evt;
      try { evt = JSON.parse(data.toString()); } catch { return; }
      if (evt.type !== 'message.deliver') return;
      if (evt.toAgentId !== AGENT_ID) return;
      if (seenMessageIds.has(evt.messageId)) return;
      seenMessageIds.add(evt.messageId);
      await deliverIncoming({
        messageId: evt.messageId,
        fromAgentName: evt.fromAgentName,
        content: evt.content,
      });
    });
    ws.on('close', (code, reason) => {
      const reasonStr = reason ? reason.toString() : '';
      clearKeepAliveTimers();
      ws = null;
      // 1008 = WS_1008_POLICY_VIOLATION (backend 의 명시적 인증 reject). 1006 등 abnormal closure 는 reconnect.
      if (code === 1008 || /401/.test(lastErrorMsg)) {
        exitOnAuthReject(`code=${code} lastError=${lastErrorMsg}`);
        return;
      }
      dbg(`aidesk-channel: ws disconnected — code=${code} reason=${reasonStr} (reconnect in ${reconnectDelay}ms)`);
      reconnectTimer = setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
    });
    ws.on('error', (err) => {
      lastErrorMsg = String(err?.message ?? err);
      dbg(`aidesk-channel: ws error ${lastErrorMsg}`);
      // npm ws 의 handshake 401 패턴 — 'Unexpected server response: 401'. close 호출 안 될 수도 있어 즉시 exit.
      if (/401/.test(lastErrorMsg)) {
        exitOnAuthReject(`error="${lastErrorMsg}"`);
      }
    });
  }
  connect();
}

// ---------------------------------------------------------------------
// 부팅
// ---------------------------------------------------------------------

dbg('about to connect transport');
const transport = new StdioServerTransport();
await server.connect(transport);
dbg('transport connected');

// 부팅 직후 helper 에게 *현재 backend URL* 확인 — claude TUI 가 오랜 시간 도는 동안
// 사용자가 backend URL 을 바꿨을 가능성에 대비. helper 응답이 더 최신이면 그걸로 갱신.
await refreshApiUrlFromHelper();

// AGENT_ID 결정 — ws subscribe 가 의존하므로 sync 완료 후 진행. 실패해도 종료 X.
dbg('about to ensureAgentId');
try {
  await ensureAgentId();
  dbg(`ensureAgentId OK — AGENT_ID=${AGENT_ID} name=${MY_AGENT_NAME}`);
} catch (e) {
  dbg(`aidesk-channel: initial agent resolve failed: ${e?.message ?? e}`);
}

dbg(`aidesk-channel ready. cwd=${process.cwd()} api=${API_URL} agent=${AGENT_ID} name=${MY_AGENT_NAME}`);

// Phase 2 — backend ws subscribe. status 토글 + 실시간 메시지 push + sampling 자동 응답.
// ws 가 *주력* — 5초 polling 은 제거 (backlog 흡수는 reconnect 시 1회로 충분).
// 초기 1회 polling 은 *기존 unread 마킹* 용 — daemon 시작 시점 이전의 메시지는 무시.
startWsSubscribe();
pollInbox(); // 즉시 1회 (백로그 마킹 — firstPoll=true 가 흡수)
