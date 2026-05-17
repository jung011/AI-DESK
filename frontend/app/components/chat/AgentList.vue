<template>
  <aside class="agent-list">
    <header class="al-head">
      <h3>대화 상대</h3>
    </header>
    <div v-if="loading" class="al-empty">로딩 중…</div>
    <div v-else-if="agents.length === 0" class="al-empty">에이전트 없음</div>
    <ul v-else class="al-list">
      <li
        v-for="a in agents"
        :key="a.agentId"
        class="al-item"
        :class="{ active: a.agentId === activeId }"
        @click="$emit('select', a.agentId)">
        <span class="al-avatar" :class="statusClass(a.status)">{{ avatar(a.status) }}</span>
        <span class="al-info">
          <span class="al-name">{{ a.agentName }}</span>
          <span class="al-meta">
            <span class="al-status" :class="statusClass(a.status)">{{ statusLabel(a.status) }}</span>
            <span class="al-model">· {{ shortModel(a.model) }}</span>
          </span>
        </span>
      </li>
    </ul>
  </aside>
</template>

<script setup lang="ts">
import type { AgentItem, AgentStatus } from '~/vo/agents/AgentVo';

defineProps<{
  agents: AgentItem[];
  activeId: string;
  loading: boolean;
}>();
defineEmits<{ (e: 'select', agentId: string): void }>();

function statusClass(s: AgentStatus): string {
  return s;
}
function statusLabel(s: AgentStatus): string {
  return { active: '작업중', waiting: '응답 대기', idle: '대기중', error: '오류' }[s] ?? s;
}
function avatar(s: AgentStatus): string {
  return { active: '🤖', waiting: '🙋', idle: '📝', error: '⚠️' }[s] ?? '📝';
}
function shortModel(m: string | null | undefined): string {
  if (!m) return '';
  return m.toLowerCase().startsWith('claude') ? 'claude' : m;
}
</script>

<style scoped>
.agent-list {
  display: flex; flex-direction: column;
  border-right: 1px solid #E5E9EF;
  background: #fff;
}
.al-head {
  padding: 16px 18px;
  border-bottom: 1px solid #F0F2F5;
}
.al-head h3 { font-size: 15px; font-weight: 700; margin: 0; color: #101010; }
.al-empty { padding: 30px 18px; color: #94A3B8; font-size: 13px; text-align: center; }

.al-list { list-style: none; padding: 0; margin: 0; flex: 1; overflow-y: auto; }
.al-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 18px; cursor: pointer;
  border-bottom: 1px solid #F5F7FA;
  transition: background 0.12s;
}
.al-item:hover { background: #F8FAFC; }
.al-item.active { background: #EEF4FF; }
.al-item.active .al-name { color: #2A50C8; font-weight: 700; }

.al-avatar {
  width: 38px; height: 38px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
  background: #F1F5F9;
}
.al-avatar.active  { background: #E8F5E9; }
.al-avatar.waiting { background: #E3F2FD; }
.al-avatar.idle    { background: #FFF8E1; }
.al-avatar.error   { background: #FFEBEE; }

.al-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.al-name {
  font-size: 14px; font-weight: 600; color: #101010;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.al-meta { font-size: 11px; color: #64748B; display: flex; gap: 4px; align-items: center; }
.al-status.active  { color: #2E7D32; font-weight: 600; }
.al-status.waiting { color: #0D47A1; font-weight: 600; }
.al-status.idle    { color: #E65100; }
.al-status.error   { color: #B71C1C; font-weight: 600; }
.al-model { color: #94A3B8; }
</style>
