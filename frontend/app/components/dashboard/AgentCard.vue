<template>
  <div class="ai-card" :class="statusClass">
    <div class="ai-card-header">
      <div class="ai-card-name-wrap">
        <div class="ai-avatar" :class="statusClass">{{ avatarEmoji }}</div>
        <div>
          <div class="ai-name">
            {{ agent.agentName }}
            <NuxtLink
              v-if="unreadCount > 0"
              :to="`/messages?withId=${encodeURIComponent(agent.agentId)}`"
              class="unread-msg-badge"
              :title="`미확인 메시지 ${unreadCount}건`">
              {{ unreadCount > 99 ? '99+' : unreadCount }}
            </NuxtLink>
          </div>
          <div class="ai-workspace" :title="agent.workspaceDir">{{ agent.workspaceDir }}</div>
        </div>
      </div>
      <span class="ico_badge small" :class="badgeClass">
        <span class="badge-dot" />{{ statusLabel }}
      </span>
    </div>

    <div class="ai-card-body">{{ agent.taskDesc ?? '—' }}</div>

    <div class="context-bar-wrap">
      <div class="context-bar-label">
        <span>컨텍스트 사용률</span>
        <strong :style="{ color: contextColor }">{{ agent.contextPct ?? 0 }}%</strong>
      </div>
      <div class="context-bar">
        <div
          class="context-bar-fill"
          :class="contextLevel"
          :style="{ width: (agent.contextPct ?? 0) + '%' }" />
      </div>
    </div>

    <div class="ai-card-footer">
      <span class="ai-model-tag">{{ agent.model }}</span>
      <div class="ai-meta">{{ metaLabel }}: <strong>{{ metaValue }}</strong></div>
      <div ref="menuRoot" class="card-menu-wrap">
        <button class="btn-card-menu" type="button" aria-label="더보기" @click.stop="menuOpen = !menuOpen">
          <span /><span /><span />
        </button>
        <div v-if="menuOpen" class="card-menu-dropdown" @click.stop>
          <button type="button" class="card-menu-item" @click="onSendMessage">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z"/></svg>
            메시지 보내기
          </button>
          <button type="button" class="card-menu-item" @click="onOpenVscode">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>
            VSCode 열기
          </button>
          <button type="button" class="card-menu-item" @click="onOpenTerminal">
            <svg class="menu-ico" viewBox="0 0 24 24" fill="currentColor"><path d="M20 4H4c-1.11 0-2 .9-2 2v12c0 1.1.89 2 2 2h16c1.11 0 2-.9 2-2V6c0-1.1-.89-2-2-2zm0 14H4V8h16v10z"/></svg>
            터미널 열기
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
import { useMessagesStore } from '~/stores/messages';

const props = defineProps<{ agent: AgentItem }>();
const emit = defineEmits<{
  (e: 'delete', agent: AgentItem): void;
  (e: 'sendMessage', agent: AgentItem): void;
}>();

const messages = useMessagesStore();
const unreadCount = computed(() => {
  const row = messages.unread.byAgent.find(a => a.agentId === props.agent.agentId);
  return row ? row.unread : 0;
});

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

function onOpenVscode(): void {
  menuOpen.value = false;
  const dir = props.agent.workspaceDir;
  if (!dir) {
    // eslint-disable-next-line no-alert
    alert('워크스페이스 경로가 비어있습니다.');
    return;
  }
  // vscode:// URI 스킴 — 브라우저가 외부 핸들러로 열어 VSCode 가 직접 처리.
  // 인코딩은 file URI 규칙에 맞춰 공백·한글 등을 안전화.
  const encoded = dir.split('/').map(encodeURIComponent).join('/');
  window.location.href = `vscode://file${encoded.startsWith('/') ? '' : '/'}${encoded}`;
}

async function onOpenTerminal(): Promise<void> {
  menuOpen.value = false;
  try {
    const { $api } = useNuxtApp();
    const env = await $api<{ result: number; message: string }>(
      `/api/agents/${encodeURIComponent(props.agent.agentId)}/open-terminal`,
      { method: 'POST' }
    );
    if (env.result !== 0) {
      // eslint-disable-next-line no-alert
      alert(env.message || '터미널 열기에 실패했습니다.');
    }
  } catch (e) {
    // eslint-disable-next-line no-alert
    alert(`터미널 열기 호출 실패: ${e instanceof Error ? e.message : String(e)}`);
  }
}

function onDelete(): void {
  menuOpen.value = false;
  emit('delete', props.agent);
}

function onSendMessage(): void {
  menuOpen.value = false;
  emit('sendMessage', props.agent);
}

const statusClass = computed(() => ({
  active: 'working',
  idle: 'idle',
  done: 'done'
}[props.agent.status] ?? 'working'));

const statusLabel = computed(() => ({
  active: '작업중',
  idle: '쉬는 중',
  done: '완료'
}[props.agent.status] ?? '작업중'));

const badgeClass = computed(() => ({
  active: 'type_v5',
  idle: 'type_v8',
  done: 'type_v9'
}[props.agent.status] ?? 'type_v5'));

const avatarEmoji = computed(() => ({
  active: '🤖',
  idle: '📝',
  done: '✅'
}[props.agent.status] ?? '🤖'));

const contextLevel = computed(() => {
  const v = props.agent.contextPct ?? 0;
  if (v >= 90) return 'high';
  if (v >= 71) return 'mid';
  return 'low';
});

const contextColor = computed(() => {
  if (contextLevel.value === 'high') return '#E53935';
  if (contextLevel.value === 'mid')  return '#E65100';
  return '#2E7D32';
});

const metaLabel = computed(() => ({
  active: '시작',
  idle: '대기 시간',
  done: '완료'
}[props.agent.status] ?? '시작'));

const metaValue = computed(() => formatTime(props.agent.startedAt, props.agent.status));

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
}
.ai-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; border-radius: 6px 6px 0 0;
}
.ai-card.working::before { background: #00C853; }
.ai-card.idle::before    { background: #FFB300; }
.ai-card.done::before    { background: #9C27B0; }

.ai-card-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.ai-card-name-wrap { display: flex; align-items: center; gap: 10px; }
.ai-avatar {
  width: 40px; height: 40px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.ai-avatar.working { background: #E8F5E9; }
.ai-avatar.idle    { background: #FFF8E1; }
.ai-avatar.done    { background: #F3E8FF; }

.ai-name {
  font-size: 15px; font-weight: 700; color: #101010; letter-spacing: -.02em;
  display: inline-flex; align-items: center; gap: 6px;
}
.unread-msg-badge {
  min-width: 18px; height: 18px; padding: 0 6px;
  border-radius: 9px; background: #E53935; color: #fff;
  font-size: 10px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none;
  cursor: pointer;
  transition: background .12s, transform .08s;
}
.unread-msg-badge:hover { background: #C42154; }
.unread-msg-badge:active { transform: scale(.95); }
.ai-workspace {
  font-size: 12px; color: #999; margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
}
.ai-card-body { font-size: 13px; color: #666; margin-bottom: 16px; line-height: 1.6; }
.ai-card-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding-top: 14px; border-top: 1px solid #F0F2F5;
}
.ai-meta { font-size: 12px; color: #AAB4BE; }
.ai-meta strong { color: #666; font-weight: 500; }

.context-bar-wrap { margin-bottom: 16px; }
.context-bar-label {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 5px;
}
.context-bar-label span { font-size: 11px; color: #AAB4BE; }
.context-bar-label strong { font-size: 12px; font-weight: 600; }
.context-bar { height: 5px; background: #F0F2F5; border-radius: 4px; overflow: hidden; }
.context-bar-fill { height: 100%; border-radius: 4px; transition: width .3s; }
.context-bar-fill.low  { background: #00C853; }
.context-bar-fill.mid  { background: #FFB300; }
.context-bar-fill.high { background: #E53935; }

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
.ico_badge.type_v5 { background: #E8F5E9; color: #2E7D32; }
.ico_badge.type_v8 { background: #FFF8E1; color: #E65100; }
.ico_badge.type_v9 { background: #F3E8FF; color: #6A1B9A; }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.ico_badge.type_v5 .badge-dot { background: #00C853; }
.ico_badge.type_v8 .badge-dot { background: #FFB300; }
.ico_badge.type_v9 .badge-dot { background: #9C27B0; }

.ai-model-tag {
  display: inline-block; padding: 2px 8px;
  border-radius: 4px; font-size: 11px; font-weight: 500;
  background: #F1F5F9; color: #64748B; font-family: monospace;
}
</style>
