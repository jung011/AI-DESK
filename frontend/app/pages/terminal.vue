<template>
  <div class="term-page">
    <header class="term-header">
      <h1>터미널</h1>
      <span class="term-subtitle">{{ activePartner ? `${activePartner.agentName} · ${activePartner.workspaceDir || '/'}` : '왼쪽에서 에이전트를 선택하세요' }}</span>
    </header>

    <div class="term-layout" :class="{ 'show-term-mobile': showTermMobile, 'list-collapsed': listCollapsed }">
      <div class="term-pane term-pane-list">
        <!-- 채팅과 동일한 AgentList 재사용. 휴먼 제외. -->
        <AgentList
          :agents="partners"
          :active-id="partnerId"
          :loading="loadingAgents"
          @select="onSelectPartner"
        />
      </div>
      <div class="term-pane term-pane-conv">
        <button class="term-collapse-btn" @click="listCollapsed = !listCollapsed"
          :title="listCollapsed ? '대화 상대 펼치기' : '대화 상대 접기'">
          {{ listCollapsed ? '▶' : '◀' }}
        </button>
        <WebTerminal
          :partner="activePartner"
          :show-back="true"
          @back="showTermMobile = false"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AgentList from '~/components/chat/AgentList.vue';
import WebTerminal from '~/components/terminal/WebTerminal.vue';
import type { AgentItem, AgentListResponse, ApiEnvelope } from '~/vo/agents/AgentVo';

const agents = ref<AgentItem[]>([]);
const currentUser = ref<AgentItem | null>(null);
const partnerId = ref<string>('');
const loadingAgents = ref(false);
const showTermMobile = ref(false);
const listCollapsed = ref(false);

const partners = computed(() =>
  agents.value.filter((a) => a.agentId !== currentUser.value?.agentId)
);
const activePartner = computed(() =>
  partners.value.find((a) => a.agentId === partnerId.value) ?? null
);

async function fetchAgents(): Promise<void> {
  loadingAgents.value = true;
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<AgentListResponse>>('/api/agents');
    if (env.result === 0 && env.data) {
      agents.value = env.data.list;
      currentUser.value = env.data.list.find((a) => a.model === 'human') ?? null;
    }
  } finally {
    loadingAgents.value = false;
  }
}

async function onSelectPartner(agentId: string): Promise<void> {
  partnerId.value = agentId;
  showTermMobile.value = true;
}

onMounted(async () => {
  await fetchAgents();
});

// agent 추가/제거 자동 갱신 — 채팅과 동일 polling (10초)
let agentPoll: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  agentPoll = setInterval(() => { void fetchAgents(); }, 10000);
});
onBeforeUnmount(() => {
  if (agentPoll) clearInterval(agentPoll);
});

function onVisibilityChange(): void {
  if (typeof document === 'undefined') return;
  if (document.visibilityState === 'visible') {
    void fetchAgents();
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
.term-page {
  display: flex; flex-direction: column;
  height: calc(100vh - 56px);
  background: linear-gradient(180deg, #0B0F19 0%, #0F1729 100%);
  color: #E5E9EE;
}
.term-header {
  padding: 18px 28px;
  border-bottom: 1px solid #1E2738;
  display: flex; align-items: center; gap: 16px;
  flex-shrink: 0;
  background: rgba(15, 23, 41, 0.6);
  backdrop-filter: blur(12px);
}
.term-header h1 {
  font-size: 18px; font-weight: 700; margin: 0;
  background: linear-gradient(90deg, #6BB6FF, #B89AFF);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.term-subtitle { font-size: 12px; color: #6B7785; }

.term-layout {
  flex: 1; display: grid;
  grid-template-columns: 300px 1fr;
  min-height: 0;
  transition: grid-template-columns .2s;
}
.term-layout.list-collapsed {
  grid-template-columns: 0 1fr;
}
.term-pane { min-height: 0; min-width: 0; display: flex; flex-direction: column; }
.term-layout.list-collapsed .term-pane-list { visibility: hidden; }

/* 접기 버튼 — terminal 패널 좌측 상단 */
.term-pane-conv { position: relative; }
.term-collapse-btn {
  position: absolute; left: 6px; top: 18px;
  z-index: 5;
  width: 22px; height: 22px;
  background: rgba(20, 28, 48, 0.7);
  border: 1px solid #2A3447;
  border-radius: 6px;
  color: #8B95A5;
  font-size: 11px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .12s, color .12s, border-color .12s;
}
.term-collapse-btn:hover {
  background: rgba(79, 127, 255, 0.15);
  border-color: #4F7FFF;
  color: #fff;
}

/* 모바일 — list 와 terminal 토글 */
@media (max-width: 768px) {
  .term-layout {
    grid-template-columns: 1fr;
    position: relative;
  }
  .term-pane-list { display: flex; }
  .term-pane-conv { display: none; }
  .term-layout.show-term-mobile .term-pane-list { display: none; }
  .term-layout.show-term-mobile .term-pane-conv { display: flex; }
}
</style>
