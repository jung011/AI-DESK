// AI Desk MCP server.
//
// 환경변수:
//   AIDESK_AGENT_ID    필수. 이 MCP 서버 인스턴스가 어느 t_ai_agent 에 해당하는지.
//   AIDESK_API_URL     선택 (기본 http://localhost:8081).
//   AIDESK_POLL_MS     선택 (기본 5000). inbox 폴링 주기.
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

const AGENT_ID = process.env.AIDESK_AGENT_ID;
const API_URL  = process.env.AIDESK_API_URL || 'http://localhost:8081';
const POLL_MS  = Number(process.env.AIDESK_POLL_MS || 5000);

if (!AGENT_ID) {
  process.stderr.write('aidesk-channel: AIDESK_AGENT_ID is not set\n');
  process.exit(3);
}

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
    description: '다른 AI 에이전트 목록을 조회합니다 (자기 자신과 done 상태는 제외).',
    inputSchema: { type: 'object', properties: {} }
  }
];

// ---------------------------------------------------------------------
// 백엔드 호출 헬퍼
// ---------------------------------------------------------------------

async function api(path, init = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) }
  });
  const env = await res.json();
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${env?.message || res.statusText}`);
  if (env.result !== 0 && !env.data) throw new Error(env.message || 'backend error');
  return env;
}

const isUuid = (s) => typeof s === 'string' && /^[0-9a-f-]{36}$/i.test(s);

async function listAgents() {
  const env = await api('/api/agents');
  return (env.data?.list || []).filter(
    (a) => a.agentId !== AGENT_ID && a.status !== 'done'
  );
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
  const toAgentId = await resolveAgentId(target_agent);
  const body = { fromAgentId: AGENT_ID, toAgentId, content };
  if (reply_to_message_id) body.replyToMessageId = reply_to_message_id;
  const env = await api('/api/messages', { method: 'POST', body: JSON.stringify(body) });
  return env.data;
}

async function replyToMessage({ message_id, content }) {
  if (!message_id || !content) throw new Error('message_id and content are required');
  const env = await api(`/api/messages/${encodeURIComponent(message_id)}`);
  const orig = env.data;
  if (!orig) throw new Error(`Original message not found: ${message_id}`);
  if (orig.toAgentId !== AGENT_ID) {
    throw new Error('You are not the receiver of this message.');
  }
  return await sendTo({
    target_agent: orig.fromAgentId,
    content,
    reply_to_message_id: message_id
  });
}

async function checkInbox({ unread_only = true, limit = 10 } = {}) {
  const url = `/api/messages?agentId=${encodeURIComponent(AGENT_ID)}&direction=inbox&limit=${encodeURIComponent(
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
    capabilities: { tools: {}, logging: {} },
    instructions:
      '이 서버는 AI Desk 의 AI 협업 채널 어댑터입니다. ' +
      '다른 AI 에게 메시지를 보낼 때 send_to, 받은 메시지(<channel> 태그)에 답할 때 reply, ' +
      '미확인 메시지를 점검할 때 check_inbox, 다른 AI 목록은 list_agents 를 사용하세요. ' +
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

const seen = new Set();
let firstPoll = true;

async function pollInbox() {
  try {
    const list = await checkInbox({ unread_only: true, limit: 20 });
    if (firstPoll) {
      list.forEach((m) => seen.add(m.messageId));
      firstPoll = false;
      return;
    }
    for (const m of list) {
      if (seen.has(m.messageId)) continue;
      seen.add(m.messageId);
      const data =
        `<channel source="aidesk-channel" task_id="${m.messageId}" from="${m.fromAgentName}">\n` +
        `${m.content}\n` +
        `</channel>`;
      try {
        await server.sendLoggingMessage({
          level: 'info',
          logger: 'aidesk-channel',
          data
        });
      } catch (e) {
        process.stderr.write(`aidesk-channel: notify failed: ${e?.message ?? e}\n`);
      }
    }
  } catch (err) {
    process.stderr.write(`aidesk-channel: poll error: ${err?.message ?? err}\n`);
  }
}

// ---------------------------------------------------------------------
// 부팅
// ---------------------------------------------------------------------

const transport = new StdioServerTransport();
await server.connect(transport);
process.stderr.write(
  `aidesk-channel ready. agent=${AGENT_ID} api=${API_URL} poll=${POLL_MS}ms\n`
);

setInterval(pollInbox, POLL_MS);
pollInbox(); // 즉시 1회 (백로그 마킹)
