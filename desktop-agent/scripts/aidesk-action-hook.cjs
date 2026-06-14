#!/usr/bin/env node
/**
 * AI Desk — Claude Code 의 PostToolUse 훅에서 mutation 액션을 백엔드에 기록.
 *
 * Claude Code 가 stdin 으로 넘기는 페이로드의 tool_name + tool_input 을 보고
 * (code|schema|file|command) 카테고리를 추정해 POST /api/action-logs 호출.
 *
 * exit code 는 항상 0 — 훅 실패가 Claude Code 동작을 멈추면 안 됨.
 */

const fs = require('fs');
const http = require('http');
const path = require('path');

const BACKEND_URL = process.env.AIDESK_BACKEND_URL || 'http://localhost:30081';

function readStdin() {
  try {
    const data = fs.readFileSync(0, 'utf-8');
    return data ? JSON.parse(data) : {};
  } catch (_) {
    return {};
  }
}

/** 파일 확장자 → code 인가 file 인가 */
const _CODE_EXT = new Set([
  '.java','.kt','.py','.vue','.ts','.tsx','.js','.jsx','.html','.css','.scss',
  '.go','.rs','.swift','.cpp','.c','.h','.rb','.php','.sql','.sh','.cjs','.mjs',
  '.xml','.yaml','.yml','.json','.toml','.md',
]);

function categorizeFilePath(p) {
  if (!p) return 'file';
  const ext = path.extname(p).toLowerCase();
  if (_CODE_EXT.has(ext)) return 'code';
  return 'file';
}

const _SQL_DDL_RE = /\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|SCHEMA|VIEW)\b|\bINSERT\s+INTO\b|\bUPDATE\s+\w+\s+SET\b|\bDELETE\s+FROM\b/i;

function categorizeBash(cmd) {
  if (!cmd) return 'command';
  if (_SQL_DDL_RE.test(cmd)) return 'schema';
  if (/^(git|rm|mv|cp|mkdir|rmdir|touch)\b/.test(cmd.trim())) return 'file';
  return 'command';
}

function categorizeDbMcp(toolName, input) {
  const text = JSON.stringify(input || {});
  if (_SQL_DDL_RE.test(text)) return 'schema';
  return 'command';
}

/** 도구 + 입력 → (category, target, summary) 추정 */
function describeAction(toolName, toolInput) {
  if (!toolName) return null;
  const t = String(toolName);

  if (t === 'Write' || t === 'Edit' || t === 'MultiEdit' || t === 'NotebookEdit') {
    const filePath = toolInput?.file_path || toolInput?.notebook_path || '';
    return {
      category: categorizeFilePath(filePath),
      target: filePath || '(unknown path)',
      summary: `${t} ${filePath || ''}`.trim(),
    };
  }

  if (t === 'Bash') {
    const cmd = String(toolInput?.command || '');
    return {
      category: categorizeBash(cmd),
      target: cmd.slice(0, 200),
      summary: `Bash: ${cmd.slice(0, 150)}`,
    };
  }

  // mcp__postgres__query, mcp__jdbc-oracle__oracle_execute 등 DB MCP 도구
  if (/^mcp__(postgres|jdbc-oracle|mysql|sqlite)__/.test(t)) {
    const query = String(toolInput?.query || toolInput?.sql || '');
    return {
      category: categorizeDbMcp(t, toolInput),
      target: query.slice(0, 200),
      summary: `${t}: ${query.slice(0, 150)}`,
    };
  }

  return null; // 관심 없는 도구 — skip
}

function postJSON(url, body) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url);
      const data = JSON.stringify(body);
      const req = http.request(
        {
          hostname: u.hostname,
          port: u.port || 80,
          path: u.pathname,
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(data),
          },
          timeout: 2000,
        },
        (res) => {
          res.on('data', () => {});
          res.on('end', () => resolve(true));
        },
      );
      req.on('error', () => resolve(false));
      req.on('timeout', () => { req.destroy(); resolve(false); });
      req.write(data);
      req.end();
    } catch (_) {
      resolve(false);
    }
  });
}

async function main() {
  const payload = readStdin();
  const toolName = payload.tool_name;
  const desc = describeAction(toolName, payload.tool_input);
  if (!desc) return; // 관심 없는 도구

  const body = {
    agentId: null,
    agentName: null,
    sessionId: payload.session_id || null,
    // cwd 는 백엔드에서 등록된 AI Desk 에이전트와 매핑하는 데 쓰임 — 매핑 안 되면 백엔드가 무시.
    cwd: payload.cwd || null,
    tool: toolName,
    category: desc.category,
    target: desc.target,
    summary: desc.summary,
  };
  await postJSON(`${BACKEND_URL.replace(/\/$/, '')}/api/action-logs`, body);
}

main().catch(() => { /* never throw */ }).finally(() => process.exit(0));
