<template>
  <aside class="agent-list">
    <header class="al-head">
      <h3>대화 상대</h3>
    </header>
    <!-- 로딩 표시는 *초기 fetch* 만. polling refresh 시 list 유지 (깜빡 방지). -->
    <div v-if="loading && agents.length === 0" class="al-empty">로딩 중…</div>
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
  return { active: '작업중', waiting: '응답 대기', idle: '대기중', offline: '오프라인', compacting: '압축 중', error: '오류' }[s] ?? s;
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
  border-right: 1px solid #1E2738;
  background: rgba(20, 28, 48, 0.5);
  flex: 1; min-height: 0;
}
.al-head {
  padding: 14px 18px;
  border-bottom: 1px solid #1E2738;
}
.al-head h3 {
  font-size: 12px; font-weight: 600; margin: 0;
  color: #8B95A5;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.al-empty { padding: 30px 18px; color: #6B7785; font-size: 13px; text-align: center; }

.al-list { list-style: none; padding: 6px 8px; margin: 0; flex: 1; overflow-y: auto; }
.al-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; cursor: pointer;
  border-radius: 8px;
  margin-bottom: 2px;
  transition: background 0.12s;
}
.al-item:hover { background: rgba(79, 127, 255, 0.08); }
.al-item.active {
  background: linear-gradient(90deg, rgba(79, 127, 255, 0.18), rgba(184, 154, 255, 0.08));
  border-left: 3px solid #4F7FFF;
  padding-left: 9px;
}
.al-item.active .al-name { color: #fff; }

.al-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; flex-shrink: 0;
  background: linear-gradient(135deg, #2A3447, #1A2030);
  border: 1px solid #2A3447;
  position: relative;
}
/* status dot */
.al-avatar::after {
  content: ''; position: absolute; bottom: 0; right: 0;
  width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid #0B0F19;
  background: #4B5563;
}
.al-avatar.active::after  { background: #10B981; }
.al-avatar.waiting::after { background: #4F7FFF; }
.al-avatar.idle::after    { background: #F59E0B; }
.al-avatar.error::after   { background: #F87171; }

.al-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.al-name {
  font-size: 13px; font-weight: 600; color: #E5E9EE;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.al-meta { font-size: 11px; color: #6B7785; display: flex; gap: 4px; align-items: center; }
.al-status.active  { color: #10B981; font-weight: 600; }
.al-status.waiting { color: #4F7FFF; font-weight: 600; }
.al-status.idle    { color: #F59E0B; }
.al-status.error   { color: #F87171; font-weight: 600; }
.al-model { color: #6B7785; }

/* scrollbar */
.al-list::-webkit-scrollbar { width: 8px; }
.al-list::-webkit-scrollbar-track { background: transparent; }
.al-list::-webkit-scrollbar-thumb { background: #2A3447; border-radius: 4px; }
.al-list::-webkit-scrollbar-thumb:hover { background: #3A4A66; }
</style>
