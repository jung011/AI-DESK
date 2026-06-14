#!/usr/bin/env node
// Claude Code 의 PreCompact / PostCompact hook.
//
// PreCompact (mode=pre):
//   - 현재 workspace 의 AGENT_ID 추출 (~/.claude.json projects[cwd].mcpServers.*.env.AIDESK_AGENT_ID)
//   - backend POST /api/agents/{id}/status { status: "compacting" } 호출
//   - additionalContext 로 LLM 에게 "memory 정리 후 압축 진행" prompt inject
//
// PostCompact (mode=post):
//   - 12초 sleep (frontend 폴링 catch 보장)
//   - 같은 endpoint 로 status='idle' 복구
//   - additionalContext 로 "MEMORY.md 의 🚨 최우선 섹션 확인 후 진행" prompt inject
//
// 사용:
//   node aidesk-compact-hook.cjs pre   # PreCompact hook
//   node aidesk-compact-hook.cjs post  # PostCompact hook

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

const mode = process.argv[2]; // 'pre' or 'post'
if (mode !== 'pre' && mode !== 'post') {
  process.stderr.write('[aidesk-compact] usage: node aidesk-compact-hook.cjs <pre|post>\n');
  process.exit(0); // hook fail 이 LLM 흐름 끊지 않게 0 exit
}

function findAgentId() {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.claude.json'), 'utf-8'));
    const proj = (data.projects || {})[process.cwd()];
    if (!proj) return null;
    const mcps = proj.mcpServers || {};
    for (const cfg of Object.values(mcps)) {
      const aid = cfg && cfg.env && cfg.env.AIDESK_AGENT_ID;
      if (aid && /^[a-f0-9-]{36}$/i.test(aid)) return aid;
    }
    return null;
  } catch {
    return null;
  }
}

function findHubUrl() {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.claude.json'), 'utf-8'));
    const proj = (data.projects || {})[process.cwd()];
    if (proj) {
      const mcps = proj.mcpServers || {};
      for (const cfg of Object.values(mcps)) {
        const url = cfg && cfg.env && cfg.env.AIDESK_API_URL;
        if (url) return url.replace(/\/$/, '');
      }
    }
  } catch { /* fallthrough */ }
  return (process.env.AIDESK_API_URL || process.env.AIDESK_HUB_URL || 'http://aidesk.kaflix.internal').replace(/\/$/, '');
}

async function postStatus(agentId, status, hubUrl) {
  try {
    const res = await fetch(`${hubUrl}/api/agents/${encodeURIComponent(agentId)}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    return res.ok;
  } catch (e) {
    process.stderr.write(`[aidesk-compact] status post failed: ${e.message}\n`);
    return false;
  }
}

(async () => {
  const agentId = findAgentId();
  const hubUrl = findHubUrl();

  if (mode === 'pre') {
    // 압축 시작 시점에 status='compacting' 으로 마킹.
    // 다른 AI 가 send_to 시 preWarning 으로 응답 지연을 인지 + dashboard 카드에
    // '압축 중 💭' 으로 표시. 메시지 자체는 tmux prompt buffer 에 큐 처리.
    if (agentId) await postStatus(agentId, 'compacting', hubUrl);
  } else {
    // PostCompact — idle 복구 전 짧게 대기. 압축이 너무 빨리 끝나면 frontend
    // 폴링이 status=compacting 한 번도 못 잡고 지나가므로 최소 12초 'compacting' 유지.
    await new Promise(r => setTimeout(r, 12000));
    if (agentId) await postStatus(agentId, 'idle', hubUrl);
  }
  process.exit(0);
})();
