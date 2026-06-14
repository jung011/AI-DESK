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
    if (agentId) await postStatus(agentId, 'compacting', hubUrl);
    const ctx = '이번 사이클의 새 패턴, 결정사항, fix 들을 memory 파일에 정리해주세요. ' +
                '정리 후 context 압축이 진행됩니다. backend status 는 compacting 으로 마킹됨 (송신자에게 응답 지연 안내).';
    process.stdout.write(JSON.stringify({ additionalContext: ctx }) + '\n');
  } else {
    // PostCompact — idle 복구 전 짧게 대기. 압축이 너무 빨리 끝나면
    // frontend 폴링이 status=compacting 한 번도 못 잡고 지나가므로
    // 시연/관찰을 위해 최소 12초 동안 'compacting' 유지 보장.
    await new Promise(r => setTimeout(r, 12000));
    if (agentId) await postStatus(agentId, 'idle', hubUrl);
    const ctx = '컨텍스트 압축 완료. MEMORY.md 의 🚨 최우선 섹션 확인 후 진행. backend status idle 로 복구.';
    process.stdout.write(JSON.stringify({ additionalContext: ctx }) + '\n');
  }
  process.exit(0);
})();
