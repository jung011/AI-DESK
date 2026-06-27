<template>
  <div class="term-page">
    <header class="term-header">
      <h1>터미널</h1>
      <span class="term-subtitle">{{ activePartner ? `${activePartner.agentName} · ${activePartner.workspaceDir || '~'}` : '왼쪽에서 에이전트를 선택하세요' }}</span>
    </header>

    <div class="term-layout" :class="{ 'show-term-mobile': showTermMobile, 'list-collapsed': listCollapsed }">
      <div class="term-pane term-pane-list">
        <button class="term-list-toggle" @click="listCollapsed = !listCollapsed"
          :title="listCollapsed ? '대화 상대 펼치기' : '대화 상대 접기'">
          {{ listCollapsed ? '▶' : '◀' }}
        </button>
        <button v-show="!listCollapsed" class="term-list-add" @click="openAddModal" title="새 터미널 추가">+</button>
        <!-- 채팅과 동일한 AgentList 재사용. 휴먼 제외. -->
        <AgentList
          v-show="!listCollapsed"
          :agents="partners"
          :active-id="partnerId"
          :loading="loadingAgents"
          @select="onSelectPartner"
          @delete="onDeleteLocal"
          @open-claude="onOpenClaude"
        />
      </div>
      <div class="term-pane term-pane-conv">
        <WebTerminal
          ref="webTermRef"
          :key="activePartner?.agentId || 'none'"
          :partner="activePartner"
          :show-back="true"
          @back="showTermMobile = false"
        />
      </div>
    </div>

    <!-- 새 터미널 추가 모달 -->
    <div v-if="showAddModal" class="add-modal-backdrop" @click.self="closeAddModal">
      <div class="add-modal">
        <h2>새 터미널</h2>
        <div class="add-modal-sub">대화 상대 패널에 표시할 이름을 입력하세요.</div>
        <input
          ref="addInputRef"
          v-model="addName"
          type="text"
          maxlength="32"
          autocomplete="off"
          placeholder="예: prod-ssh, scratch, log-tail"
          @keydown.enter="commitAdd"
          @keydown.escape="closeAddModal" />
        <div class="add-modal-buttons">
          <button class="amb-btn" @click="closeAddModal">취소</button>
          <button class="amb-btn amb-primary" :disabled="!addName.trim()" @click="commitAdd">추가</button>
        </div>
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

// 로컬 터미널 (localStorage) — claude 없이 zsh 만 띄우는 임시 워크스페이스.
type LocalTerminal = { id: string; name: string; createdAt: string };
const LOCAL_TERMINAL_KEY = 'aidesk-terminal-bookmarks';
const localTerminals = ref<LocalTerminal[]>([]);
function loadLocalTerminals(): void {
  if (typeof localStorage === 'undefined') return;
  try {
    const raw = localStorage.getItem(LOCAL_TERMINAL_KEY);
    localTerminals.value = raw ? JSON.parse(raw) : [];
  } catch {
    localTerminals.value = [];
  }
}
function saveLocalTerminals(): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(LOCAL_TERMINAL_KEY, JSON.stringify(localTerminals.value));
}
function toShellAgent(t: LocalTerminal): AgentItem {
  return {
    agentId: t.id,
    agentName: t.name,
    workspaceDir: '',                       // helper 가 $HOME 사용
    tmuxSession: `aidesk-shell-${t.id}`,    // ai agent 의 aidesk-{agentId} 와 분리
    status: 'idle',
    taskDesc: null,
    model: 'shell',
    contextPct: null,
    startedAt: t.createdAt,
    updatedAt: null,
  };
}

const partners = computed(() => {
  const ai = agents.value.filter((a) => a.agentId !== currentUser.value?.agentId);
  const local = localTerminals.value.map(toShellAgent);
  return [...ai, ...local];
});
const activePartner = computed(() =>
  partners.value.find((a) => a.agentId === partnerId.value) ?? null
);

// 추가 모달
const showAddModal = ref(false);
const addName = ref('');
const addInputRef = ref<HTMLInputElement | null>(null);
function openAddModal(): void {
  addName.value = '';
  showAddModal.value = true;
  nextTick(() => addInputRef.value?.focus());
}
function closeAddModal(): void {
  showAddModal.value = false;
}
function commitAdd(): void {
  const name = addName.value.trim();
  if (!name) return;
  const id = 'shell-' + Math.random().toString(36).slice(2, 10);
  localTerminals.value.push({ id, name, createdAt: new Date().toISOString() });
  saveLocalTerminals();
  closeAddModal();
  // 자동 진입 — 추가하자마자 그 터미널로 포커스 이동
  partnerId.value = id;
  showTermMobile.value = true;
}
function onDeleteLocal(agentId: string): void {
  localTerminals.value = localTerminals.value.filter((t) => t.id !== agentId);
  saveLocalTerminals();
  if (partnerId.value === agentId) partnerId.value = '';
}

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

// 햄버거 메뉴 → 클로드 열기 — WebTerminal 의 textarea 에 명령어 자동 입력.
// AgentList 의 select 가 먼저 처리됨 (active partner 변경) → ref 의 pasteCommand 호출.
// dev/macOS = Agent Teams 분할창 활성. *옛 대화 있을 때만* -c 박음
// (없으면 `No conversation found to continue` 에러).
const webTermRef = ref<{ pasteCommand?: (text: string) => void } | null>(null);
async function onOpenClaude(agentId: string): Promise<void> {
  const agent = partners.value.find((p: AgentItem) => p.agentId === agentId);
  let hasPast = false;
  if (agent?.workspaceDir) {
    try {
      // prod = 127.0.0.1:30083 사용자 mac local helper. frontend hostname (kaflix.internal)
      // 가리키면 ingress 30083 listen X → fetch fail → hasPast=false → `-c` 안 박음.
      // WebTerminal.vue / AgentCardTerminal.vue 와 동일 분기 패턴.
      const helperBase = import.meta.dev
        ? `http://${window.location.hostname}:30084`
        : 'http://127.0.0.1:30083';
      const url = `${helperBase}/api/has-past-session?workspaceDir=${encodeURIComponent(agent.workspaceDir)}`;
      const res = await fetch(url);
      const body = await res.json() as { hasPast?: boolean };
      hasPast = !!body.hasPast;
    } catch (_e) {
      hasPast = false;  // fail-safe = `-c` 안 박음
    }
  }
  await nextTick();
  setTimeout(() => {
    const continueFlag = hasPast ? ' -c' : '';
    // Agent Teams 분할창 flag (--teammate-mode tmux) 는 ~/.claude/settings.json
    // 의 teammateMode=auto 가 *환경 자동 검출* — 명령어 안 박음.
    const cmd = `claude --dangerously-load-development-channels server:aidesk-channel${continueFlag}`;
    webTermRef.value?.pasteCommand?.(cmd);
  }, 600);
}

onMounted(async () => {
  loadLocalTerminals();
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
  grid-template-columns: 220px 1fr;
  min-height: 0;
  transition: grid-template-columns .2s;
}
.term-layout.list-collapsed {
  grid-template-columns: 36px 1fr;
}
.term-pane { min-height: 0; min-width: 0; display: flex; flex-direction: column; }

/* 접기 버튼 — 대화상대 박스 좌측 상단 (펼친 / 접힌 상태 둘 다 visible) */
.term-pane-list { position: relative; }
.term-list-toggle {
  position: absolute; top: 14px; right: 8px;
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
.term-list-toggle:hover {
  background: rgba(79, 127, 255, 0.15);
  border-color: #4F7FFF;
  color: #fff;
}
.term-layout.list-collapsed .term-list-toggle {
  /* 접힌 상태에서는 right 보다 가운데 정렬이 자연 */
  right: 7px; left: 7px;
}

/* + 아이콘 — 토글 button 좌측 */
.term-list-add {
  position: absolute; top: 14px; right: 36px;
  z-index: 5;
  width: 22px; height: 22px;
  background: rgba(79, 127, 255, 0.12);
  border: 1px solid #2A3447;
  border-radius: 6px;
  color: #6BB6FF;
  font-size: 16px; line-height: 1;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .12s, color .12s, border-color .12s;
}
.term-list-add:hover {
  background: rgba(79, 127, 255, 0.25);
  border-color: #4F7FFF;
  color: #fff;
}

/* 추가 모달 */
.add-modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.add-modal {
  background: linear-gradient(180deg, #14172A 0%, #0F1729 100%);
  border: 1px solid #2A3447;
  border-radius: 12px;
  padding: 24px;
  width: 360px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.6);
}
.add-modal h2 {
  margin: 0 0 6px;
  font-size: 16px; font-weight: 700;
  color: #E5E9EE;
}
.add-modal-sub {
  font-size: 12px; color: #6B7785;
  margin-bottom: 16px;
}
.add-modal input {
  width: 100%;
  background: rgba(20, 28, 48, 0.7);
  border: 1px solid #2A3447;
  border-radius: 8px;
  padding: 10px 12px;
  color: #E5E9EE;
  font-size: 14px;
  outline: none;
  transition: border-color .12s;
}
.add-modal input:focus { border-color: #4F7FFF; }
.add-modal-buttons {
  margin-top: 18px;
  display: flex; gap: 8px; justify-content: flex-end;
}
.amb-btn {
  padding: 8px 16px;
  border: 1px solid #2A3447;
  background: transparent;
  color: #8B95A5;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  transition: all .12s;
}
.amb-btn:hover { background: rgba(255, 255, 255, 0.04); color: #E5E9EE; }
.amb-primary {
  background: #4F7FFF;
  border-color: #4F7FFF;
  color: #fff;
}
.amb-primary:hover { background: #3D6BEE; border-color: #3D6BEE; }
.amb-primary:disabled {
  background: #2A3447; border-color: #2A3447;
  color: #6B7785;
  cursor: not-allowed;
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
