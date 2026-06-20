<template>
  <section class="term-view">
    <header v-if="partner" class="tv-head">
      <button v-if="showBack" class="tv-back" @click="$emit('back')" aria-label="뒤로">←</button>
      <span class="tv-avatar" :class="partner.status">{{ avatar(partner.status) }}</span>
      <div class="tv-title">
        <div class="tv-name">{{ partner.agentName }}</div>
        <div class="tv-meta">
          <span class="tv-status-dot" :class="partner.status"></span>
          <span>{{ statusLabel(partner.status) }}</span>
          <span class="tv-meta-sep">·</span>
          <code class="tv-cwd">{{ partner.workspaceDir || '/' }}</code>
        </div>
      </div>
    </header>
    <header v-else class="tv-head empty">
      <span class="tv-placeholder">터미널을 열 에이전트를 왼쪽에서 선택하세요</span>
    </header>

    <div v-if="partner" class="tv-body">
      <div class="tv-statusbar">
        <span class="tv-dots">
          <span class="d-red"></span><span class="d-yel"></span><span class="d-grn"></span>
        </span>
        <span class="tv-name-small">{{ partner.agentName }}</span>
        <span class="tv-meta-small">{{ partner.workspaceDir || '/' }} · 80×24</span>
        <div class="tv-right">
          <span class="tv-conn">준비 중</span>
        </div>
      </div>
      <div class="tv-placeholder-area">
        <p class="tv-todo">TA-2 단계에서 xterm.js + WebSocket pty 연결됩니다.</p>
        <p class="tv-todo-sub">선택된 에이전트의 workspaceDir 로 새 shell 시작 예정</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { AgentItem, AgentStatus } from '~/vo/agents/AgentVo';

defineProps<{
  partner: AgentItem | null;
  showBack: boolean;
}>();

defineEmits<{ (e: 'back'): void }>();

function statusLabel(s: AgentStatus): string {
  return { active: '작업중', waiting: '응답 대기', idle: '대기중', offline: '오프라인', compacting: '압축 중', error: '오류' }[s] ?? s;
}
function avatar(s: AgentStatus): string {
  return { active: '🤖', waiting: '🙋', idle: '📝', error: '⚠️' }[s] ?? '📝';
}
</script>

<style scoped>
.term-view {
  display: flex; flex-direction: column;
  background: rgba(15, 23, 41, 0.4);
  flex: 1; min-width: 0; min-height: 0;
}

.tv-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 22px;
  background: rgba(20, 28, 48, 0.3);
  border-bottom: 1px solid #1E2738;
  flex-shrink: 0;
}
.tv-head.empty { justify-content: center; color: #6B7785; }
.tv-placeholder { font-size: 13px; }
.tv-back {
  display: none; padding: 6px 10px;
  background: transparent; border: none; cursor: pointer;
  font-size: 18px; color: #8B95A5;
}
.tv-avatar {
  width: 38px; height: 38px; border-radius: 50%;
  background: linear-gradient(135deg, #2A3447, #1A2030);
  border: 1px solid #2A3447;
  display: flex; align-items: center; justify-content: center; font-size: 18px;
}
.tv-title { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.tv-name { font-size: 14px; font-weight: 700; color: #E5E9EE; }
.tv-meta {
  font-size: 11px; color: #8B95A5;
  display: inline-flex; align-items: center; gap: 5px;
}
.tv-meta-sep { color: #4B5563; }
.tv-cwd {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px; color: #6BB6FF;
  background: rgba(79, 127, 255, 0.08);
  padding: 1px 6px; border-radius: 4px;
}
.tv-status-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #4B5563; flex-shrink: 0;
}
.tv-status-dot.active   { background: #10B981; box-shadow: 0 0 6px rgba(16, 185, 129, 0.6); }
.tv-status-dot.waiting  { background: #4F7FFF; box-shadow: 0 0 6px rgba(79, 127, 255, 0.6); }
.tv-status-dot.idle     { background: #F59E0B; }
.tv-status-dot.offline  { background: #4B5563; }
.tv-status-dot.error    { background: #F87171; }

.tv-body {
  flex: 1; min-height: 0;
  padding: 24px 28px;
  display: flex; flex-direction: column;
}

.tv-statusbar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px;
  background: rgba(20, 28, 48, 0.6);
  border: 1px solid #1F2738;
  border-bottom: none;
  border-radius: 14px 14px 0 0;
  font-size: 12px; color: #8B95A5;
}
.tv-dots { display: flex; gap: 6px; }
.tv-dots span { width: 11px; height: 11px; border-radius: 50%; }
.tv-dots .d-red { background: #F87171; }
.tv-dots .d-yel { background: #F59E0B; }
.tv-dots .d-grn { background: #10B981; }
.tv-name-small { font-weight: 600; color: #E5E9EE; }
.tv-meta-small { color: #6B7785; font-size: 11px; font-family: ui-monospace, SFMono-Regular, monospace; }
.tv-right { margin-left: auto; }
.tv-conn {
  font-size: 11px; color: #F59E0B;
}

.tv-placeholder-area {
  flex: 1;
  background: #0E1424;
  border: 1px solid #1F2738;
  border-top: none;
  border-radius: 0 0 14px 14px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 28px;
}
.tv-todo { font-size: 14px; color: #C5CDD8; }
.tv-todo-sub { font-size: 12px; color: #6B7785; }

/* 모바일 */
@media (max-width: 768px) {
  .tv-back { display: block; }
}
</style>
