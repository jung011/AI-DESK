<template>
  <div class="task-panel">
    <div class="task-panel-head">
      <div class="task-panel-title">📋 작업 큐 <span class="task-panel-count">({{ visibleTasks.length }} / {{ list.length }})</span></div>
      <button class="task-add-btn" @click="modalOpen = true">＋ Task 추가</button>
    </div>
    <table class="task-table">
      <thead>
        <tr>
          <th style="width:55%">태스크명</th>
          <th style="width:25%">담당자</th>
          <th style="width:20%">상태</th>
        </tr>
      </thead>
      <tbody :class="{ scrollable: expanded }">
        <tr v-for="t in visibleTasks" :key="t.taskId" class="task-row" :class="t.status">
          <td>
            <div class="task-content">{{ t.content }}</div>
            <div v-if="t.attachments.length > 0" class="task-att-row">
              <span v-for="a in t.attachments" :key="a.attachmentId" class="task-att-chip">📎 {{ a.originalFilename }}</span>
            </div>
          </td>
          <td>
            <span class="task-owner">{{ t.agentName ?? t.agentId.slice(0, 8) }}</span>
          </td>
          <td>
            <span class="task-status" :class="t.status">{{ statusLabel(t.status) }}</span>
          </td>
        </tr>
        <tr v-if="list.length === 0">
          <td colspan="3" class="task-empty">아직 박힌 task 가 없어요. ＋ Task 추가 박아 시작!</td>
        </tr>
      </tbody>
    </table>
    <div v-if="list.length > COLLAPSED_LIMIT" class="task-expand-row" @click="expanded = !expanded">
      {{ expanded ? '▲ 접기' : `＋ 더 보기 (${list.length - COLLAPSED_LIMIT} 개 숨김)` }}
    </div>

    <TaskCreateModal
      :open="modalOpen"
      :agents="agents"
      @close="modalOpen = false"
      @created="onCreated" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { TaskStatus } from '~/vo/tasks/TaskVo';
import type { AgentItem } from '~/vo/agents/AgentVo';
import TaskCreateModal from '~/components/dashboard/TaskCreateModal.vue';

const props = defineProps<{ agents: AgentItem[] }>();
const { list, fetchRecent } = useTasks();

const modalOpen = ref(false);
const expanded = ref(false);
const COLLAPSED_LIMIT = 4;

const visibleTasks = computed(() =>
  expanded.value ? list.value : list.value.slice(0, COLLAPSED_LIMIT)
);
const agents = computed(() => props.agents);

function statusLabel(s: TaskStatus): string {
  switch (s) {
    case 'todo': return '▶ TODO';
    case 'in_progress': return '⚙ IN-PROGRESS';
    case 'done': return '✓ DONE';
    case 'stuck': return '⚠ STUCK';
    case 'canceled': return '✕ CANCELED';
    default: return s;
  }
}

function onCreated(): void {
  modalOpen.value = false;
  void fetchRecent();
}
</script>

<style scoped>
.task-panel {
  background: rgba(15, 23, 41, 0.6);
  border: 1px solid #1E2738;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 20px;
}
.task-panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.task-panel-title { font-size: 13px; font-weight: 600; color: #E5EBF5; }
.task-panel-count { color: #6B7280; font-weight: 400; margin-left: 6px; }
.task-add-btn { background: #2A4A8E; color: white; border: none; border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer; font-weight: 600; }
.task-add-btn:hover { background: #3A5A9E; }
.task-table { width: 100%; border-collapse: collapse; }
.task-table thead th { text-align: left; font-size: 10px; color: #6B7280; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; padding: 6px 10px; border-bottom: 1px solid #1E2738; }
.task-table tbody.scrollable { display: block; max-height: 240px; overflow-y: auto; }
.task-table thead, .task-table tbody tr { display: table; width: 100%; table-layout: fixed; }
.task-table tbody td { padding: 8px 10px; font-size: 12px; border-bottom: 1px solid #1E2738; vertical-align: top; }
.task-row.done td { color: #6B7280; }
.task-row.done .task-content { text-decoration: line-through; }
.task-row.canceled td { color: #6B7280; opacity: 0.6; }
.task-content { color: #E5EBF5; line-height: 1.4; }
.task-att-row { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px; }
.task-att-chip { background: rgba(42, 74, 142, 0.18); border: 1px solid rgba(42, 74, 142, 0.4); color: #93C5FD; padding: 1px 6px; border-radius: 4px; font-size: 10px; }
.task-owner { color: #93C5FD; }
.task-status { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
.task-status.todo { background: rgba(107, 114, 128, 0.2); color: #9CA3AF; }
.task-status.in_progress { background: rgba(251, 191, 36, 0.2); color: #FBBF24; }
.task-status.done { background: rgba(16, 185, 129, 0.2); color: #34D399; }
.task-status.stuck { background: rgba(239, 68, 68, 0.2); color: #FCA5A5; }
.task-status.canceled { background: rgba(75, 85, 99, 0.2); color: #9CA3AF; }
.task-empty { text-align: center; color: #6B7280; padding: 24px 10px; font-style: italic; }
.task-expand-row { text-align: center; padding: 8px; color: #93C5FD; cursor: pointer; font-size: 12px; border-top: 1px solid #1E2738; }
.task-expand-row:hover { background: rgba(42, 74, 142, 0.15); }
</style>
