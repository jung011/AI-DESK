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

    <div class="ai-card-footer">
      <span class="ai-model-tag" :class="modelClass">{{ modelLabel }}</span>
      <div class="ai-meta">{{ metaLabel }}: <strong>{{ metaValue }}</strong></div>
      <div ref="menuRoot" class="card-menu-wrap">
        <button class="btn-card-menu" type="button" aria-label="더보기" @click.stop="menuOpen = !menuOpen">
          <span /><span /><span />
        </button>
        <div v-if="menuOpen" class="card-menu-dropdown" @click.stop>
          <button type="button" class="card-menu-item" @click="onOpenVscode">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>
            VSCode 열기
          </button>
          <button type="button" class="card-menu-item" @click="onOpenTerminal">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M20 4H4c-1.11 0-2 .9-2 2v12c0 1.1.89 2 2 2h16c1.11 0 2-.9 2-2V6c0-1.1-.89-2-2-2zm0 14H4V8h16v10z"/></svg>
            외부 터미널 열기
          </button>
          <button type="button" class="card-menu-item" @click="onPlaceholder('브라우저 검증')">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/></svg>
            브라우저 검증
          </button>
          <div class="card-menu-divider" />
          <button type="button" class="card-menu-item danger" @click="onDelete">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
            삭제
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgentItem } from '~/vo/agents/AgentVo';
const props = defineProps<{ agent: AgentItem }>();
const emit = defineEmits<{
  (e: 'delete', agent: AgentItem): void;
  (e: 'select', agent: AgentItem): void;
}>();

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

async function onOpenTerminal(): Promise<void> {
  menuOpen.value = false;
  try {
    const { $helper } = useNuxtApp();
    const env = await $helper<{ rc: number; message: string }>(
      '/api/open-terminal',
      {
        method: 'POST',
        body: {
          workspaceDir: props.agent.workspaceDir,
          tmuxSession: props.agent.tmuxSession,
          title: props.agent.agentName,
        },
      }
    );
    if (env.rc !== 0) {
      // eslint-disable-next-line no-alert
      alert(env.message || '터미널 열기에 실패했습니다.');
    }
  } catch (e) {
    // eslint-disable-next-line no-alert
    alert(`터미널 열기 호출 실패 (헬퍼 가동 확인): ${e instanceof Error ? e.message : String(e)}`);
  }
}

function onDelete(): void {
  menuOpen.value = false;
  emit('delete', props.agent);
}

const statusClass = computed(() => ({
  active: 'working',
  waiting: 'waiting',
  idle: 'idle',
  done: 'done',
  error: 'error'
}[props.agent.status] ?? 'working'));

const statusLabel = computed(() => ({
  active: '작업중',
  waiting: '응답 대기',
  idle: '쉬는 중',
  done: '완료',
  error: '오류'
}[props.agent.status] ?? '작업중'));

const badgeClass = computed(() => ({
  active: 'type_v5',
  waiting: 'type_v10',
  idle: 'type_v8',
  done: 'type_v9',
  error: 'type_v11'
}[props.agent.status] ?? 'type_v5'));

const avatarEmoji = computed(() => ({
  active: '🤖',
  waiting: '🙋',
  idle: '📝',
  done: '✅',
  error: '⚠️'
}[props.agent.status] ?? '🤖'));

const metaLabel = computed(() => ({
  active: '시작',
  waiting: '대기 시작',
  idle: '대기 시간',
  done: '완료',
  error: '오류 발생'
}[props.agent.status] ?? '시작'));

const metaValue = computed(() => formatTime(props.agent.startedAt, props.agent.status));

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
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
  padding: 20px; box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .12);
  position: relative;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s, transform .08s;
}
.ai-card:hover { border-color: #0062ff; box-shadow: 0 6px 18px rgba(0, 98, 255, .15); }
.ai-card:active { transform: scale(.995); }
.ai-card:focus-visible { outline: 2px solid #0062ff; outline-offset: 2px; }
/* 메뉴 열렸을 때 — 드롭다운이 다음 행 카드 뒤에 깔리지 않도록 카드 자체를 위로 끌어올림.
 * (.ai-card 가 position:relative + z-index:auto 라 형제 카드와 DOM 순서로 쌓이는 문제 보정) */
.ai-card.menu-open { z-index: 100; }
.ai-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; border-radius: 6px 6px 0 0;
}
.ai-card.working::before { background: #00C853; }
.ai-card.waiting::before { background: #0062FF; }
.ai-card.idle::before    { background: #FFB300; }
.ai-card.done::before    { background: #9C27B0; }
.ai-card.error::before   { background: #E53935; }

.ai-card-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.ai-card-name-wrap { display: flex; align-items: center; gap: 10px; }
.ai-avatar {
  width: 40px; height: 40px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.ai-avatar.working { background: #E8F5E9; }
.ai-avatar.waiting { background: #E3F2FD; }
.ai-avatar.idle    { background: #FFF8E1; }
.ai-avatar.done    { background: #F3E8FF; }
.ai-avatar.error   { background: #FFEBEE; }

.ai-name {
  font-size: 15px; font-weight: 700; color: #101010; letter-spacing: -.02em;
  display: inline-flex; align-items: center; gap: 6px;
}
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
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
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
.ico_badge.type_v5  { background: #E8F5E9; color: #2E7D32; }
.ico_badge.type_v8  { background: #FFF8E1; color: #E65100; }
.ico_badge.type_v9  { background: #F3E8FF; color: #6A1B9A; }
.ico_badge.type_v10 { background: #E3F2FD; color: #0D47A1; }
.ico_badge.type_v11 { background: #FFEBEE; color: #B71C1C; }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.ico_badge.type_v5  .badge-dot { background: #00C853; }
.ico_badge.type_v8  .badge-dot { background: #FFB300; }
.ico_badge.type_v9  .badge-dot { background: #9C27B0; }
.ico_badge.type_v10 .badge-dot { background: #0062FF; }
.ico_badge.type_v11 .badge-dot { background: #E53935; }

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
