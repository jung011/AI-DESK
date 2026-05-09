<template>
  <div class="page_content">
    <!-- 페이지 헤더 -->
    <div class="group_pageLocation">
      <h2 class="tit_h2">대시보드</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>대시보드</em></a>
      </div>
      <div style="margin-left: auto;">
        <button type="button" class="btn normal type_v1" @click="dialogOpen = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:6px"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" /></svg>
          AI 생성
        </button>
      </div>
    </div>

    <!-- 요약 카드 -->
    <SummaryCardGrid :summary="summary" />

    <!-- 필터 탭 + 이름 검색 -->
    <FilterBar
      :status="status"
      :query="query"
      @update:status="status = $event"
      @update:query="query = $event" />

    <div v-if="error" class="error-box">
      백엔드 호출 실패: {{ error }}
    </div>

    <!-- AI 카드 그리드 -->
    <AgentCardGrid
      :agents="filteredList"
      @delete="onDeleteRequest"
      @sendMessage="onSendMessageRequest" />

    <!-- AI 생성 팝업 -->
    <AgentCreateDialog
      :open="dialogOpen"
      :submitting="creating"
      :error-message="createError"
      @close="dialogOpen = false"
      @submit="onCreateSubmit" />

    <!-- 삭제 확인 팝업 -->
    <ConfirmDialog
      :open="confirmDelete.open"
      title="AI 삭제"
      :message="confirmDelete.message"
      confirm-label="삭제"
      :destructive="true"
      :busy="deleting"
      @cancel="closeDeleteDialog"
      @confirm="onDeleteConfirm" />

    <!-- 새 메시지 팝업 (카드 메뉴에서 진입) -->
    <NewMessageDialog
      :open="newMsg.open"
      :agents="list"
      :initial-to-agent-id="newMsg.toAgentId"
      :lock-to="true"
      :submitting="newMsg.submitting"
      :error-message="newMsg.error"
      @close="closeNewMessage"
      @submit="onSendNewMessage" />
  </div>
</template>

<script setup lang="ts">
import { useAgents } from '~/composables/useAgents';
import { useMessagesStore } from '~/stores/messages';
import SummaryCardGrid from '~/components/dashboard/SummaryCardGrid.vue';
import FilterBar from '~/components/dashboard/FilterBar.vue';
import AgentCardGrid from '~/components/dashboard/AgentCardGrid.vue';
import AgentCreateDialog from '~/components/dashboard/AgentCreateDialog.vue';
import ConfirmDialog from '~/components/common/ConfirmDialog.vue';
import NewMessageDialog from '~/components/messages/NewMessageDialog.vue';

import type { AgentCreateRequest, AgentItem } from '~/vo/agents/AgentVo';
import type { MessageBroadcastRequest } from '~/vo/messages/MessageVo';

const {
  list,
  summary,
  status,
  query,
  filteredList,
  error,
  startPolling,
  stopPolling,
  createAgent,
  deleteAgent
} = useAgents();

const messagesStore = useMessagesStore();

const dialogOpen = ref(false);
const creating = ref(false);
const createError = ref<string | null>(null);

const confirmDelete = reactive<{ open: boolean; agent: AgentItem | null; message: string }>({
  open: false,
  agent: null,
  message: ''
});
const deleting = ref(false);

async function onCreateSubmit(req: AgentCreateRequest): Promise<void> {
  creating.value = true;
  createError.value = null;
  const created = await createAgent(req);
  creating.value = false;
  if (created) {
    dialogOpen.value = false;
  } else {
    createError.value = error.value ?? '생성에 실패했습니다.';
  }
}

function onDeleteRequest(agent: AgentItem): void {
  confirmDelete.agent = agent;
  confirmDelete.message = `${agent.agentName}을(를) 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`;
  confirmDelete.open = true;
}

function closeDeleteDialog(): void {
  if (deleting.value) return;
  confirmDelete.open = false;
  confirmDelete.agent = null;
}

async function onDeleteConfirm(): Promise<void> {
  if (!confirmDelete.agent || deleting.value) return;
  deleting.value = true;
  const ok = await deleteAgent(confirmDelete.agent.agentId);
  deleting.value = false;
  if (ok) {
    confirmDelete.open = false;
    confirmDelete.agent = null;
  }
  // 실패 시는 error 메시지가 useAgents.error 에 채워지고, 페이지 상단에 표시됨.
}

const newMsg = reactive<{
  open: boolean;
  toAgentId: string | null;
  submitting: boolean;
  error: string | null;
}>({
  open: false,
  toAgentId: null,
  submitting: false,
  error: null
});

function onSendMessageRequest(agent: AgentItem): void {
  newMsg.toAgentId = agent.agentId;
  newMsg.error = null;
  newMsg.open = true;
}

function closeNewMessage(): void {
  if (newMsg.submitting) return;
  newMsg.open = false;
  newMsg.toAgentId = null;
}

async function onSendNewMessage(req: MessageBroadcastRequest): Promise<void> {
  newMsg.submitting = true;
  newMsg.error = null;
  const result = await messagesStore.sendBroadcast(req);
  newMsg.submitting = false;
  if (result) {
    newMsg.open = false;
    newMsg.toAgentId = null;
  } else {
    newMsg.error = messagesStore.error ?? '발신 실패';
  }
}

onMounted(() => startPolling(10_000));
onUnmounted(() => stopPolling());
</script>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}
.group_pageLocation {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.tit_h2 {
  font-size: 20px;
  font-weight: 700;
  color: #101010;
  margin: 0;
}
.descList_pageLocation {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94A3B8;
}
.descList_pageLocation a {
  color: #94A3B8;
  text-decoration: none;
}
.descList_pageLocation a + a::before {
  content: '›';
  margin-right: 6px;
  color: #CBD5E1;
}
.descList_pageLocation em {
  font-style: normal;
  color: #475569;
  font-weight: 600;
}
.btn.normal {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
}
.btn.normal.type_v1 {
  background: #0062ff;
  color: #fff;
}
.btn.normal.type_v1:hover { background: #0052d4; }
.btn.normal.type_v1:disabled { background: #94A3B8; cursor: not-allowed; }

.error-box {
  margin-bottom: 20px;
  padding: 12px 16px;
  border-radius: 6px;
  background: #FFE5E9;
  border: 1px solid #FFB4BD;
  color: #B22B45;
  font-size: 13px;
}
</style>
