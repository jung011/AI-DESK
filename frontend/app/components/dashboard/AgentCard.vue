<template>
  <div class="ai-card" :class="statusClass">
    <div class="ai-card-header">
      <div class="ai-card-name-wrap">
        <div class="ai-avatar" :class="statusClass">{{ avatarEmoji }}</div>
        <div>
          <div class="ai-name">{{ agent.agentName }}</div>
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
      <button class="btn-card-menu" type="button" aria-label="더보기" disabled>
        <span /><span /><span />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgentItem } from '~/vo/agents/AgentVo';

const props = defineProps<{ agent: AgentItem }>();

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

// 컨텍스트 % 임계값 — low 0~70 / mid 71~89 / high 90~100
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

// 상태별 메타 라벨
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
  // active / done — HH:mm
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

.ai-name { font-size: 15px; font-weight: 700; color: #101010; letter-spacing: -.02em; }
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

.btn-card-menu {
  width: 30px; height: 30px; border-radius: 6px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 3.5px; background: none; border: none; cursor: pointer;
  position: relative;
}
.btn-card-menu:disabled { cursor: not-allowed; opacity: .5; }
.btn-card-menu span {
  display: block; width: 14px; height: 1.5px;
  background: #AAB4BE; border-radius: 2px;
}

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
