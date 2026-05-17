<template>
  <div class="chat-page">
    <header class="chat-header">
      <h1>채팅</h1>
      <span class="chat-subtitle">휴먼(나) ↔ 내부 AI · (me) 리키 포함</span>
    </header>

    <div class="chat-layout" :class="{ 'show-conv-mobile': showConvMobile }">
      <div class="chat-pane chat-pane-list">
        <AgentList
          :agents="partners"
          :active-id="partnerId"
          :loading="loadingAgents"
          @select="onSelectPartner"
        />
      </div>
      <div class="chat-pane chat-pane-conv">
        <ConversationView
          :partner="activePartner"
          :messages="messages"
          :me-id="currentUser?.agentId ?? ''"
          :loading="loadingMessages"
          :sending="sending"
          :show-back="true"
          @send="onSend"
          @back="showConvMobile = false"
        />
      </div>
    </div>

    <div v-if="error" class="chat-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import AgentList from '~/components/chat/AgentList.vue';
import ConversationView from '~/components/chat/ConversationView.vue';

const {
  agents, currentUser, partnerId, messages,
  loadingAgents, loadingMessages, sending, error,
  fetchAgents, fetchMessages, selectPartner, send, startPolling, stopPolling,
} = useChat();

// 휴먼(사용자 본인)만 제외 — (me) 리키도 채팅 가능한 partner 로 노출.
const partners = computed(() =>
  agents.value.filter((a) => a.agentId !== currentUser.value?.agentId)
);

const activePartner = computed(() =>
  partners.value.find((a) => a.agentId === partnerId.value) ?? null
);

// 모바일: 사이드바 ↔ 본문 토글
const showConvMobile = ref(false);

async function onSelectPartner(agentId: string): Promise<void> {
  await selectPartner(agentId);
  showConvMobile.value = true;
}

async function onSend(content: string): Promise<void> {
  await send(content);
}

onMounted(async () => {
  await fetchAgents();
  startPolling();
});

onBeforeUnmount(() => {
  stopPolling();
});

// 에이전트 목록도 주기적으로 갱신 (status 변경 반영)
let agentPoll: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  agentPoll = setInterval(() => { void fetchAgents(); }, 10000);
});
onBeforeUnmount(() => {
  if (agentPoll) clearInterval(agentPoll);
});

// 모바일 PWA 가 백그라운드 가면 OS 가 setInterval 을 멈춤.
// 화면이 다시 보이는 순간 즉시 최신 메시지/에이전트를 한번 가져오고 polling 재시작.
// (이 핸들러가 없으면 모바일에서 잠금 후 복귀 시 한참 동안 새 메시지 안 보임)
function onVisibilityChange(): void {
  if (typeof document === 'undefined') return;
  if (document.visibilityState === 'visible') {
    void fetchAgents();
    void fetchMessages();
    startPolling();
  } else {
    stopPolling();
  }
}
onMounted(() => {
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange);
  }
});
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibilityChange);
  }
});
</script>

<style scoped>
.chat-page {
  display: flex; flex-direction: column;
  height: calc(100vh - 56px);
  background: #fff;
}
.chat-header {
  padding: 18px 24px; border-bottom: 1px solid #E5E9EF;
  display: flex; align-items: baseline; gap: 12px;
  flex-shrink: 0;
}
.chat-header h1 { font-size: 22px; font-weight: 700; margin: 0; }
.chat-subtitle { font-size: 12px; color: #64748B; }

.chat-layout {
  flex: 1; display: grid;
  grid-template-columns: 300px 1fr;
  min-height: 0;
}
.chat-pane { min-height: 0; min-width: 0; display: flex; flex-direction: column; }

.chat-error {
  padding: 10px 16px; background: #FEE2E2; color: #B91C1C;
  font-size: 13px; text-align: center;
}

/* 모바일 — agentList 와 conversation 을 토글 */
@media (max-width: 768px) {
  .chat-layout {
    grid-template-columns: 1fr;
    position: relative;
  }
  .chat-pane-list { display: flex; }
  .chat-pane-conv {
    display: none;
  }
  .chat-layout.show-conv-mobile .chat-pane-list { display: none; }
  .chat-layout.show-conv-mobile .chat-pane-conv { display: flex; }
}
</style>
