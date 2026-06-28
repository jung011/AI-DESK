<template>
  <div class="ai-card" :class="[statusClass, { 'menu-open': menuOpen }]" role="button" tabindex="0" @click="onSelect" @keydown.enter="onSelect" @keydown.space.prevent="onSelect">
    <div class="ai-card-header">
      <div class="ai-card-name-wrap">
        <div class="ai-avatar" :class="statusClass">{{ avatarEmoji }}</div>
        <div>
          <div class="ai-name">{{ agent.agentName }}</div>
        </div>
      </div>
      <span class="ico_badge small" :class="badgeClass">
        <span class="badge-dot" />{{ statusLabel }}
      </span>
    </div>

    <div v-if="agent.contextPct != null" class="ctx-bar-wrap" :title="`컨텍스트 ${agent.contextPct}%`">
      <span class="ctx-label">컨텍스트</span>
      <div class="ctx-bar">
        <div class="ctx-fill" :class="ctxLevel" :style="{ width: agent.contextPct + '%' }" />
      </div>
      <span class="ctx-pct" :class="ctxLevel">{{ agent.contextPct }}%</span>
    </div>

    <!-- mini terminal preview (read-only) — helper /ws/terminal attach -->
    <AgentCardTerminal
      v-if="terminalEnabled"
      :agent-id="agent.agentId"
      :tmux-session="agent.tmuxSession || `aidesk-${agent.agentId.slice(0, 8)}`"
      :workspace-dir="agent.workspaceDir || ''"
      :agent-name="agent.agentName"
    />

    <div class="ai-card-footer">
      <span class="ai-model-tag" :class="modelClass">{{ modelLabel }}</span>
      <div class="ai-meta">{{ metaLabel }}: <strong>{{ metaValue }}</strong></div>
      <div ref="menuRoot" class="card-menu-wrap">
        <button class="btn-card-menu" type="button" aria-label="더보기" @click.stop="menuOpen = !menuOpen">
          <span /><span /><span />
        </button>
        <div v-if="menuOpen" class="card-menu-dropdown" @click.stop>
          <!-- VSCode 열기 / 브라우저 검증: 당분간 사용 안 함 (2026-06-19 비활성).
               helper /api/open-vscode 라우트 + onPlaceholder/onOpenVscode 함수도 같이 주석.
          <button type="button" class="card-menu-item" @click="onOpenVscode">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>
            VSCode 열기
          </button>
          -->
          <!-- 외부 터미널 열기: 2026-06-21 비활성 (웹 터미널로 대체). 부활 시 이 button + 아래
               TerminalModeDialog + script 의 callOpenTerminal/onOpenTerminal/onModeConfirm/
               onModeCancel/modeDialogOpen/modeDialogBusy + TerminalModeDialog import 모두 해제.
          <button type="button" class="card-menu-item" @click="onOpenTerminal">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M20 4H4c-1.11 0-2 .9-2 2v12c0 1.1.89 2 2 2h16c1.11 0 2-.9 2-2V6c0-1.1-.89-2-2-2zm0 14H4V8h16v10z"/></svg>
            외부 터미널 열기
          </button>
          -->
          <!--
          <button type="button" class="card-menu-item" @click="onPlaceholder('브라우저 검증')">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/></svg>
            브라우저 검증
          </button>
          -->
          <div class="card-menu-divider" />
          <button type="button" class="card-menu-item danger" @click="onDelete">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
            삭제
          </button>
        </div>
      </div>
    </div>
    <!-- 외부 터미널 모드 선택 dialog — 외부 터미널 열기 비활성과 같이 주석.
    <TerminalModeDialog
      :open="modeDialogOpen"
      :busy="modeDialogBusy"
      @confirm="onModeConfirm"
      @cancel="onModeCancel"
    />
    -->
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { AgentItem } from '~/vo/agents/AgentVo';
import AgentCardTerminal from '~/components/dashboard/AgentCardTerminal.vue';
// 외부 터미널 열기 비활성 (2026-06-21) — 부활 시 import + 아래 type / function 모두 해제.
// import TerminalModeDialog from '~/components/dashboard/TerminalModeDialog.vue';

// type OpenTerminalEnv = {
//   rc: number;
//   message?: string;
//   needsModeSelection?: boolean;
// };
// type WorkroleEnv = { result: number; data?: { path: string } | null };

const props = defineProps<{ agent: AgentItem }>();
const emit = defineEmits<{
  (e: 'delete', agent: AgentItem): void;
  (e: 'select', agent: AgentItem): void;
}>();

// mini terminal preview — human (사람) / 외부 환경 agent 제외. tmux session 있어야.
const terminalEnabled = computed(() => {
  if ((props.agent.model || '').toLowerCase() === 'human') return false;
  if (!props.agent.tmuxSession && !props.agent.agentId) return false;
  // offline status 도 표시 시도 — 빈 화면 보일 수 있지만 reconnect 가능
  return true;
});

function onSelect(): void {
  if (menuOpen.value) return; // 메뉴 떠 있을 땐 카드 선택 무시
  emit('select', props.agent);
}

const menuOpen = ref(false);
const menuRoot = ref<HTMLElement | null>(null);

function handleClickOutside(e: MouseEvent): void {
  if (!menuOpen.value) return;
  const root = menuRoot.value;
  if (root && !root.contains(e.target as Node)) {
    menuOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});
onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});

// VSCode 열기 / 브라우저 검증: 당분간 사용 안 함 (2026-06-19 비활성).
// 부활 시 카드 메뉴 dropdown 의 두 버튼 (template) 도 함께 주석 해제.
/*
function onPlaceholder(label: string): void {
  menuOpen.value = false;
  // eslint-disable-next-line no-alert
  alert(`${label}는 후속 단계에 구현됩니다.`);
}

async function onOpenVscode(): Promise<void> {
  menuOpen.value = false;
  try {
    const { $helper } = useNuxtApp();
    const env = await $helper<{ rc: number; message: string }>(
      '/api/open-vscode',
      {
        method: 'POST',
        body: { workspaceDir: props.agent.workspaceDir },
      }
    );
    if (env.rc !== 0) {
      // eslint-disable-next-line no-alert
      alert(env.message || 'VSCode 열기에 실패했습니다.');
    }
  } catch (e) {
    // eslint-disable-next-line no-alert
    alert(`VSCode 열기 호출 실패 (헬퍼 가동 확인): ${e instanceof Error ? e.message : String(e)}`);
  }
}
*/

/*
// 외부 터미널 열기 — 2026-06-21 비활성 (웹 터미널로 대체). 부활 시 전체 block + template +
// import + types 모두 주석 해제.
//
// 외부 터미널 열기 호출.
// - mode 미지정 (첫 시도): 살아있으면 attach + 포커스 (200), 죽었으면 helper 가 412 (needsModeSelection)
// - mode 지정 (모달 confirm 후): helper 가 그 모드로 tmux+claude 시작 + attach
//
// helper 가 새로 띄울 때 첫 부팅이면 identity/workrole 자동 주입 — 그래서 mode 지정 호출 시에만
// agentName / workroleFile 도 같이 전달한다.
async function callOpenTerminal(
  mode = '',
  customOpts = '',
): Promise<OpenTerminalEnv & { needsModeSelection?: boolean }> {
  const { $helper, $api } = useNuxtApp();
  const body: Record<string, unknown> = {
    workspaceDir: props.agent.workspaceDir,
    tmuxSession: props.agent.tmuxSession,
    title: props.agent.agentName,
    // PoC v1 — helper 가 봇 어댑터 spawn 시 backend WS 인증용 agentId 필요.
    agentId: props.agent.agentId,
  };
  if (mode) {
    body.mode = mode;
    if (customOpts) body.customOpts = customOpts;
    body.agentName = props.agent.agentName;
    // workrole 은 인증 cookie 가 있는 $api 로 조회. 실패해도 진행 (identity 만 주입됨).
    try {
      const wrEnv = await $api<WorkroleEnv>('/api/settings/workrole-file');
      if (wrEnv.result === 0 && wrEnv.data) body.workroleFile = wrEnv.data.path || '';
    } catch {
      // workrole 조회 실패 무시
    }
  }
  try {
    return await $helper<OpenTerminalEnv>('/api/open-terminal', { method: 'POST', body });
  } catch (e: unknown) {
    // $fetch 는 412 같은 non-2xx 를 throw — 모드 선택 신호를 분리 처리.
    const err = e as { statusCode?: number; status?: number; data?: OpenTerminalEnv };
    const status = err?.statusCode ?? err?.status;
    const data = err?.data;
    if (status === 412 && data?.needsModeSelection) {
      return { ...data };
    }
    throw e;
  }
}

const modeDialogOpen = ref(false);
const modeDialogBusy = ref(false);

async function onOpenTerminal(): Promise<void> {
  menuOpen.value = false;
  try {
    const env = await callOpenTerminal();
    if (env.needsModeSelection) {
      modeDialogOpen.value = true;
    } else if (env.rc !== 0) {
      alert(env.message || '터미널 열기에 실패했습니다.');
    }
  } catch (e) {
    alert(`터미널 열기 호출 실패 (헬퍼 가동 확인): ${e instanceof Error ? e.message : String(e)}`);
  }
}

async function onModeConfirm(payload: { mode: string; customOpts: string }): Promise<void> {
  modeDialogBusy.value = true;
  try {
    const env = await callOpenTerminal(payload.mode, payload.customOpts);
    if (env.rc === 0) {
      modeDialogOpen.value = false;
    } else {
      alert(env.message || '터미널 시작에 실패했습니다.');
    }
  } catch (e) {
    alert(`터미널 시작 실패: ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    modeDialogBusy.value = false;
  }
}

function onModeCancel(): void {
  modeDialogOpen.value = false;
}
*/

function onDelete(): void {
  menuOpen.value = false;
  emit('delete', props.agent);
}

// 3 layer 통합 — 온라인은 단일 색 (working). compacting = waiting (별도 톤 유지).
const statusClass = computed(() => ({
  active: 'working',
  waiting: 'working',
  idle: 'working',
  offline: 'offline',
  compacting: 'waiting',
  error: 'error'
}[props.agent.status] ?? 'working'));

// 3 layer 통합: 온라인 (active/waiting/idle) / 오프라인 / 압축중.
const statusLabel = computed(() => ({
  active: '온라인',
  waiting: '온라인',
  idle: '온라인',
  offline: '오프라인',
  compacting: '압축중',
  error: '오류'
}[props.agent.status] ?? '온라인'));

// 온라인 3 상태 (active/waiting/idle) = 모두 초록 type_v5. 옛 idle→type_v8 (gray) 사고
// 가 *온라인이지만 회색* 박힘으로 offline 과 구분 안가. 통일 = statusLabel 의 *온라인 묶음*
// 과 정합.
const badgeClass = computed(() => ({
  active: 'type_v5',
  waiting: 'type_v5',
  idle: 'type_v5',
  offline: 'type_v8',
  compacting: 'type_v10',
  error: 'type_v11'
}[props.agent.status] ?? 'type_v8'));

const avatarEmoji = computed(() => ({
  active: '🤖',
  waiting: '🙋',
  idle: '📝',
  offline: '💤',
  compacting: '💭',
  error: '⚠️'
}[props.agent.status] ?? '📝'));

const metaLabel = computed(() => ({
  active: '시작',
  waiting: '대기 시작',
  idle: '대기 시간',
  error: '오류 발생'
}[props.agent.status] ?? '시작'));

const metaValue = computed(() => formatTime(props.agent.startedAt, props.agent.status));

/** context_pct 의 threshold 색 — 60 미만 green, 60~85 orange, 85+ red. */
const ctxLevel = computed(() => {
  const p = props.agent.contextPct ?? 0;
  if (p >= 85) return 'level-high';
  if (p >= 60) return 'level-mid';
  return 'level-low';
});

/** 모델별 색상 구분 — 풀네임에서 prefix 만 매칭. 알 수 없는 모델은 기본 회색. */
const modelClass = computed(() => {
  const m = (props.agent.model || '').toLowerCase();
  if (m.startsWith('claude')) return 'model-claude';
  if (m === 'codex')          return 'model-codex';
  if (m === 'hermes')         return 'model-hermes';
  return '';
});

/** 카드에 표시할 짧은 모델명. `claude-opus-4-7` → `claude`, 그 외는 원본 그대로. */
const modelLabel = computed(() => {
  const m = (props.agent.model || '');
  return m.toLowerCase().startsWith('claude') ? 'claude' : m;
});

function formatTime(iso: string, status: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (status === 'idle') {
    const minutes = Math.max(1, Math.round((Date.now() - d.getTime()) / 60_000));
    if (minutes < 60) return `${minutes}분`;
    if (minutes < 60 * 24) return `${Math.round(minutes / 60)}시간`;
    return `${Math.round(minutes / 60 / 24)}일`;
  }
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}
</script>

<style scoped>
.ai-card {
  background: rgba(15, 23, 41, 0.6); border: 1px solid var(--border-soft); border-radius: 12px;
  padding: 20px; box-shadow: none;
  position: relative;
  cursor: pointer;
  transition: border-color .15s, transform .15s;
}
.ai-card:hover { border-color: #6BB6FF; transform: translateY(-2px); }
.ai-card:active { transform: scale(.995); }
.ai-card:focus-visible { outline: 2px solid #6BB6FF; outline-offset: 2px; }
/* 메뉴 열렸을 때 — 드롭다운이 다음 행 카드 뒤에 깔리지 않도록 카드 자체를 위로 끌어올림.
 * (.ai-card 가 position:relative + z-index:auto 라 형제 카드와 DOM 순서로 쌓이는 문제 보정) */
.ai-card.menu-open { z-index: 100; }
.ai-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; border-radius: 6px 6px 0 0;
}
/* 상단 3px line — 온라인 (working) = 초록, 압축중 = 파랑, 에러 = 빨강. offline = 없음 */
.ai-card.working::before { background: #10B981; }
.ai-card.waiting::before { background: #6BB6FF; }
.ai-card.idle::before    { background: #10B981; }
.ai-card.error::before   { background: #F87171; }
.ai-card.offline::before { background: transparent; }

.ai-card-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.ai-card-name-wrap { display: flex; align-items: center; gap: 10px; }
.ai-avatar {
  width: 40px; height: 40px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.ai-avatar.working { background: rgba(16, 185, 129, 0.2); }
.ai-avatar.waiting { background: rgba(107, 182, 255, 0.2); }
.ai-avatar.idle    { background: rgba(251, 191, 36, 0.2); }
.ai-avatar.error   { background: rgba(239, 68, 68, 0.2); }

.ai-name {
  font-size: 15px; font-weight: 700; color: var(--text); letter-spacing: -.02em;
  display: inline-flex; align-items: center; gap: 6px;
}
/* 컨텍스트 사용량 — 5h 사용량과 달리 agent 별 별도값. */
.ctx-bar-wrap {
  display: flex; align-items: center; gap: 8px;
  margin: 4px 0 12px;
}
.ctx-label {
  font-size: 11px; color: var(--text-muted); flex-shrink: 0;
}
.ctx-bar {
  flex: 1; height: 6px; border-radius: 3px;
  background: var(--border-soft); overflow: hidden;
}
.ctx-fill { height: 100%; transition: width .2s ease; }
.ctx-fill.level-low  { background: #10B981; }
.ctx-fill.level-mid  { background: #F59E0B; }
.ctx-fill.level-high { background: #EF4444; }
.ctx-pct {
  font-size: 11px; font-weight: 600; min-width: 32px; text-align: right;
}
.ctx-pct.level-low  { color: #059669; }
.ctx-pct.level-mid  { color: #D97706; }
.ctx-pct.level-high { color: #DC2626; }

.ai-card-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding-top: 14px; border-top: 1px solid #F0F2F5;
}
.ai-meta { font-size: 12px; color: #AAB4BE; }
.ai-meta strong { color: #666; font-weight: 500; }

.card-menu-wrap { position: relative; }
.btn-card-menu {
  width: 30px; height: 30px; border-radius: 6px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 3.5px; background: none; border: none; cursor: pointer;
}
.btn-card-menu:hover { background: #F1F5F9; }
.btn-card-menu span {
  display: block; width: 14px; height: 1.5px;
  background: #AAB4BE; border-radius: 2px;
}
.card-menu-dropdown {
  position: absolute; top: 36px; right: 0;
  width: 180px;
  background: var(--bg-card); border: 1px solid #D4DCE4; border-radius: 6px;
  box-shadow: 0 6px 18px 0 rgba(67, 87, 103, .18);
  padding: 4px 0; z-index: 50;
  display: flex; flex-direction: column;
}
.card-menu-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  font-size: 13px; color: #333;
  text-align: left; background: none; border: none; cursor: pointer;
}
.card-menu-item:hover:not(:disabled) { background: #F8FAFC; }
.card-menu-item:disabled { color: #94A3B8; cursor: not-allowed; }
.card-menu-item.danger { color: #E83667; }
.card-menu-item .menu-ico {
  width: 14px; height: 14px; flex-shrink: 0; opacity: .7;
}
.card-menu-divider { height: 1px; background: #F0F2F5; margin: 4px 0; }

.ico_badge.small {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 600;
}
/* 다크 정합 + 사용자 spec 통일 (옛 옅은 light → alpha 다크):
   - 온라인 (active/waiting/idle → type_v5) = 초록
   - 오프라인 (type_v8) = 회색 (옛 노랑 → 회색 통일)
   - 압축중 (type_v10) = 파랑
   - 에러 (type_v11) = 빨강 */
.ico_badge.type_v5  { background: rgba(16, 185, 129, 0.18); color: #34D399; }
.ico_badge.type_v8  { background: rgba(107, 114, 128, 0.22); color: #9CA3AF; }
.ico_badge.type_v9  { background: rgba(168, 85, 247, 0.18); color: #C084FC; }
.ico_badge.type_v10 { background: rgba(107, 182, 255, 0.18); color: #6BB6FF; }
.ico_badge.type_v11 { background: rgba(248, 113, 113, 0.18); color: #F87171; }
.badge-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
/* 점등 — 온라인 (type_v5) 만 초록 glow ON. 오프라인 (type_v8) = 점등 OFF (display:none).
   압축중 / 에러 도 같은 초록 dot (옛 통일 spec 유지). 8px 크기 + strong glow 박아 visible. */
.ico_badge.type_v5  .badge-dot { background: #22C55E; box-shadow: 0 0 6px #22C55E, 0 0 2px rgba(34,197,94,0.8); }
.ico_badge.type_v8  .badge-dot { display: none; }
.ico_badge.type_v9  .badge-dot { background: #22C55E; box-shadow: 0 0 4px rgba(34,197,94,0.5); }
.ico_badge.type_v10 .badge-dot { background: #22C55E; box-shadow: 0 0 4px rgba(34,197,94,0.5); }
.ico_badge.type_v11 .badge-dot { background: #22C55E; box-shadow: 0 0 4px rgba(34,197,94,0.5); }

.ai-model-tag {
  display: inline-block; padding: 2px 8px;
  border-radius: 4px; font-size: 11px; font-weight: 500;
  background: #F1F5F9; color: #64748B; font-family: monospace;
}
/* 모델별 컬러 — 카드를 흘긋 봐도 어떤 모델인지 즉시 식별. */
.ai-model-tag.model-claude { background: #FEF3C7; color: #92400E; }  /* amber  — Anthropic 톤 */
.ai-model-tag.model-codex  { background: #D1FAE5; color: #065F46; }  /* green  — OpenAI 톤 */
.ai-model-tag.model-hermes { background: #EDE9FE; color: #5B21B6; }  /* purple — Nous 톤 */
</style>
