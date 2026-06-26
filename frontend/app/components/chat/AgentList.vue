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
        :class="{ active: a.agentId === activeId, 'al-item-shell': a.model === 'shell' }"
        @click="$emit('select', a.agentId)">
        <span class="al-avatar" :class="statusClass(a.status)">{{ avatar(a.status, a.model) }}</span>
        <span class="al-info">
          <span class="al-name">{{ a.agentName }}</span>
          <span class="al-meta">
            <span class="al-status" :class="statusClass(a.status)">{{ statusLabel(a.status) }}</span>
            <span class="al-model">· {{ shortModel(a.model) }}</span>
          </span>
        </span>
        <!-- 햄버거 메뉴 — claude agent 만 (shell 은 의미 없음). hover 시 표시. -->
        <button
          v-if="a.model !== 'shell'"
          class="al-menu-btn"
          title="메뉴"
          @click.stop="toggleMenu(a.agentId)">⋯</button>
        <div
          v-if="menuOpenId === a.agentId"
          class="al-menu-dropdown"
          @click.stop>
          <button class="al-menu-item" @click="onOpenClaude(a.agentId)">
            <span class="al-menu-ico">▶</span>클로드 열기
          </button>
        </div>
        <button
          v-if="a.model === 'shell'"
          class="al-del"
          title="터미널 삭제"
          @click.stop="$emit('delete', a.agentId)">×</button>
      </li>
    </ul>
  </aside>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import type { AgentItem, AgentStatus } from '~/vo/agents/AgentVo';

defineProps<{
  agents: AgentItem[];
  activeId: string;
  loading: boolean;
}>();
const emit = defineEmits<{
  (e: 'select', agentId: string): void;
  (e: 'delete', agentId: string): void;
  (e: 'open-claude', agentId: string): void;
}>();

// 햄버거 dropdown — 현재 열린 카드의 agentId. 동시에 1개만.
const menuOpenId = ref<string | null>(null);
function toggleMenu(agentId: string): void {
  menuOpenId.value = menuOpenId.value === agentId ? null : agentId;
}
function onOpenClaude(agentId: string): void {
  menuOpenId.value = null;
  emit('select', agentId);   // 해당 agent 의 터미널로 select
  emit('open-claude', agentId);
}

function handleClickOutside(): void {
  menuOpenId.value = null;
}
onMounted(() => { document.addEventListener('click', handleClickOutside); });
onUnmounted(() => { document.removeEventListener('click', handleClickOutside); });

function statusClass(s: AgentStatus): string {
  return s;
}
function statusLabel(s: AgentStatus): string {
  return { active: '작업중', waiting: '응답 대기', idle: '대기중', offline: '오프라인', compacting: '압축 중', error: '오류' }[s] ?? s;
}
function avatar(s: AgentStatus, model?: string | null): string {
  if (model === 'shell') return '💻';
  return { active: '🤖', waiting: '🙋', idle: '📝', error: '⚠️' }[s] ?? '📝';
}
function shortModel(m: string | null | undefined): string {
  if (!m) return '';
  if (m === 'shell') return 'zsh';
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

/* agent item position relative — dropdown 의 absolute positioning anchor */
.al-item { position: relative; }

/* 햄버거 메뉴 버튼 — hover 시 표시 */
.al-menu-btn {
  width: 22px; height: 22px;
  background: transparent;
  border: 0;
  color: #8B95A5;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  border-radius: 6px;
  visibility: hidden;
  flex-shrink: 0;
}
.al-item:hover .al-menu-btn,
.al-item.active .al-menu-btn { visibility: visible; }
.al-menu-btn:hover { color: #E5E9EE; background: rgba(79, 127, 255, 0.1); }

.al-menu-dropdown {
  position: absolute;
  top: 100%; right: 8px;
  background: #1A2030;
  border: 1px solid #2A3447;
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  z-index: 20;
  min-width: 140px;
}
.al-menu-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%;
  background: transparent;
  border: 0;
  padding: 8px 10px;
  color: #E5E9EE;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
}
.al-menu-item:hover { background: rgba(79, 127, 255, 0.15); }
.al-menu-ico { font-size: 10px; color: #6BB6FF; }

/* shell 항목 — hover 시 delete 버튼 표시 */
.al-item-shell {}
.al-del {
  width: 22px; height: 22px;
  background: transparent;
  border: 0;
  color: #6B7785;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  border-radius: 6px;
  visibility: hidden;
  flex-shrink: 0;
}
.al-item-shell:hover .al-del { visibility: visible; }
.al-del:hover { color: #F87171; background: rgba(248, 113, 113, 0.08); }

/* scrollbar */
.al-list::-webkit-scrollbar { width: 8px; }
.al-list::-webkit-scrollbar-track { background: transparent; }
.al-list::-webkit-scrollbar-thumb { background: #2A3447; border-radius: 4px; }
.al-list::-webkit-scrollbar-thumb:hover { background: #3A4A66; }
</style>
