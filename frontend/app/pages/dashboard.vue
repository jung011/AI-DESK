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

    <!-- 로컬 통합 Claude 사용량 -->
    <LocalUsageBar />

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

    <!-- view 모드 토글 — 카드 grid / wiring -->
    <div class="view-toggle">
      <button type="button" :class="['toggle-btn', viewMode === 'grid' ? 'active' : '']" @click="viewMode = 'grid'">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z"/></svg>
        Grid
      </button>
      <button type="button" :class="['toggle-btn', viewMode === 'wiring' ? 'active' : '']" @click="viewMode = 'wiring'">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 8c-1.66 0-3 1.34-3 3 0 .34.06.66.16.97l-3.32 3.32c-.31-.1-.63-.16-.97-.16-.34 0-.66.06-.97.16L7.59 12c.1-.31.16-.63.16-.97 0-1.66-1.34-3-3-3s-3 1.34-3 3 1.34 3 3 3c.34 0 .66-.06.97-.16l3.32 3.32c-.1.31-.16.63-.16.97 0 1.66 1.34 3 3 3s3-1.34 3-3c0-.34-.06-.66-.16-.97l3.32-3.32c.31.1.63.16.97.16 1.66 0 3-1.34 3-3s-1.34-3-3-3z"/></svg>
        Wiring
      </button>
    </div>

    <!-- AI 카드 그리드 -->
    <AgentCardGrid
      v-if="viewMode === 'grid'"
      :agents="filteredList"
      @delete="onDeleteRequest"
      @select="onAgentSelect" />
    <AgentWiringView
      v-else
      :agents="filteredList"
      @delete="onDeleteRequest"
      @select="onAgentSelect" />

    <!-- 사내 동료 AI (자체 채널 — 조회 전용. 메시지는 외부 터미널의 (me) claude 가 mcp send_to). -->
    <ColleagueGrid />

    <!-- 임베드 터미널 + VSCode 사이드 패널 — 사용 빈도 낮아 잠시 비활성.
         외부 터미널 열기 / 외부 VSCode 열기 (AgentCard 안 버튼) 흐름은 그대로 동작.
         복원하려면 아래 블록의 주석만 풀면 됨.
    <TerminalSidePanel
      :open="panel.open"
      :agent-name="panel.agentName"
      :subtitle="panel.subtitle"
      :tmux-session="panel.tmuxSession"
      :workspace-dir="panel.workspaceDir"
      :model="panel.model"
      @close="panel.open = false" />
    -->


    <!-- helper 가 가리키는 중앙서버가 현재 페이지와 다르면 자동 표시 — IP 변경 자동 반영. -->
    <HelperSetupDialog
      :open="helperSetupOpen"
      :current-backend-url="helperBackendUrl"
      :page-origin="pageOrigin"
      @applied="onHelperSetupApplied"
      @cancel="helperSetupOpen = false" />

    <!-- (me) 워크스페이스 미지정 또는 (me) row 부재 시 자동 표시되는 모달 -->
    <MeWorkspaceDialog
      :open="meWorkspaceDialogOpen"
      :initial-path="meWorkspacePath"
      :me-agent-missing="meAgentMissing"
      @saved="onMeWorkspaceSaved"
      @cancel="meWorkspaceDialogOpen = false" />

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
      extra-option-label="이 워크스페이스의 Claude 대화 기록도 함께 삭제"
      :extra-option-default="true"
      @cancel="closeDeleteDialog"
      @confirm="onDeleteConfirm" />
  </div>
</template>

<script setup lang="ts">
import { useAgents } from '~/composables/useAgents';
import SummaryCardGrid from '~/components/dashboard/SummaryCardGrid.vue';
import FilterBar from '~/components/dashboard/FilterBar.vue';
import LocalUsageBar from '~/components/dashboard/LocalUsageBar.vue';
import AgentCardGrid from '~/components/dashboard/AgentCardGrid.vue';
import AgentWiringView from '~/components/dashboard/AgentWiringView.vue';

const viewMode = ref<'grid' | 'wiring'>('grid');
import AgentCreateDialog from '~/components/dashboard/AgentCreateDialog.vue';
import ConfirmDialog from '~/components/common/ConfirmDialog.vue';
import ColleagueGrid from '~/components/dashboard/ColleagueGrid.vue';
import MeWorkspaceDialog from '~/components/dashboard/MeWorkspaceDialog.vue';
import HelperSetupDialog from '~/components/dashboard/HelperSetupDialog.vue';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
interface A2aWorkspaceRs { path: string }
interface HelperLocalInfoRs { currentBackendUrl?: string }
// 임베드 터미널 + 임베드 VSCode 사이드 패널 비활성 — TerminalSidePanel + 하위
// TerminalPane / VsCodePane 까지 함께 bundle 에서 빠지도록 import 도 같이 주석.
// 복원하려면 이 import 와 template 안의 <TerminalSidePanel> 블록 주석 해제.
// import TerminalSidePanel from '~/components/dashboard/TerminalSidePanel.vue';

import type { AgentCreateRequest, AgentItem } from '~/vo/agents/AgentVo';

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
  deleteAgent,
  fetchAgents
} = useAgents();

const meWorkspacePath = ref('');
const meWorkspaceDialogOpen = ref(false);
const meAgentMissing = ref(false);

const helperSetupOpen = ref(false);
const helperBackendUrl = ref('');
const pageOrigin = ref('');

/** helper 의 backend URL host 와 brower origin host 가 다르면 setup 모달.
 *  같은 host 면 port 차이는 무시 (frontend:30080 vs backend:30081).
 *
 *  subpath 배포 (예: https://도메인/ai-desk) 의 경우 hubUrl 에 baseURL 도 포함해서
 *  helper 에 전달해야 helper 가 /api/* 호출 시 그 prefix 를 자동으로 붙인다. */
async function checkHelperSetup(): Promise<void> {
  if (typeof window === 'undefined') return;
  const runtime = useRuntimeConfig();
  const baseURL = (runtime.app?.baseURL || '/').replace(/\/+$/, '');
  pageOrigin.value = window.location.origin + baseURL;
  try {
    const { $helper } = useNuxtApp();
    const info = await $helper<HelperLocalInfoRs>('/api/local-info');
    helperBackendUrl.value = info.currentBackendUrl || '';
    if (!helperBackendUrl.value) return; // 옛 helper (0.6.7-) 호환 — 모달 안 띄움
    const helperUrl = new URL(helperBackendUrl.value);
    const pageUrl = new URL(pageOrigin.value || window.location.origin);
    const helperPath = helperUrl.pathname.replace(/\/+$/, '');
    const pagePath = pageUrl.pathname.replace(/\/+$/, '');
    // host 또는 path prefix 가 다르면 mismatch → setup 모달.
    if (helperUrl.hostname !== pageUrl.hostname || helperPath !== pagePath) {
      helperSetupOpen.value = true;
    }
  } catch {
    // helper 미가동 등 — 무시. (me) 모달 단계의 폴더 선택에서 어차피 에러로 안내됨.
  }
}

function onHelperSetupApplied(): void {
  // helper 가 launchctl 재로드 + brower 가 3s 후 자동 새로고침. 그 동안 다른 모달 숨김.
  helperSetupOpen.value = false;
  meWorkspaceDialogOpen.value = false;
}

/** (me) AI 는 tmux_session 이 'aidesk-self-' 로 시작. list 에 존재 여부로 판정. */
function hasMeAgent(): boolean {
  return list.value.some((a) => a.tmuxSession?.startsWith('aidesk-self-'));
}

async function loadMeWorkspace(): Promise<void> {
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<A2aWorkspaceRs>>('/api/settings/a2a-workspace');
    if (env.result === 0 && env.data) {
      meWorkspacePath.value = env.data.path || '';
    }
  } catch {
    // 조회 실패해도 모달 강제 표시는 하지 않음 — 네트워크 일시 오류일 수 있음.
    return;
  }
  // path 가 비어있거나 (me) row 가 없으면 모달 자동 표시. (me) 가 사라진 케이스는
  // 사용자가 카드를 직접 삭제했거나 DB 가 정합성 어긋난 상태.
  const missing = !hasMeAgent();
  meAgentMissing.value = missing && meWorkspacePath.value !== '';
  if (!meWorkspacePath.value || missing) {
    meWorkspaceDialogOpen.value = true;
  }
}

async function onMeWorkspaceSaved(path: string): Promise<void> {
  meWorkspacePath.value = path;
  meAgentMissing.value = false;
  meWorkspaceDialogOpen.value = false;
  await fetchAgents();
}

const dialogOpen = ref(false);
const creating = ref(false);
const createError = ref<string | null>(null);

const confirmDelete = reactive<{ open: boolean; agent: AgentItem | null; message: string }>({
  open: false,
  agent: null,
  message: ''
});
const deleting = ref(false);

/** 임베드 터미널 사이드 패널 상태. agentId/employeeId 변할 때 TerminalPane 재마운트 되도록 :key 가 tmuxSession 에 묶여있음. */
const panel = reactive<{
  open: boolean;
  agentName: string;
  subtitle: string;
  tmuxSession: string;
  workspaceDir: string;
  model: string;
}>({ open: false, agentName: '', subtitle: '', tmuxSession: '', workspaceDir: '', model: '' });

function onAgentSelect(agent: AgentItem): void {
  panel.agentName = agent.agentName;
  panel.subtitle = `${agent.model}  ·  ${agent.workspaceDir || '워크스페이스 미설정'}`;
  panel.tmuxSession = agent.tmuxSession || `aidesk-${agent.agentId.slice(0, 8)}`;
  panel.workspaceDir = agent.workspaceDir || '';
  panel.model = agent.model || '';
  panel.open = true;
}


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
  confirmDelete.message = `${agent.agentName}을(를) 삭제하시겠습니까?\n\n· DB 에서 영구 제거됩니다 (메시지 기록 포함)\n· 실행 중인 claude 세션과 터미널 창도 함께 종료됩니다`;
  confirmDelete.open = true;
}

function closeDeleteDialog(): void {
  if (deleting.value) return;
  confirmDelete.open = false;
  confirmDelete.agent = null;
}

async function onDeleteConfirm(payload: { extraOption: boolean }): Promise<void> {
  if (!confirmDelete.agent || deleting.value) return;
  deleting.value = true;
  const ok = await deleteAgent(confirmDelete.agent, { purgeHistory: payload.extraOption });
  deleting.value = false;
  if (ok) {
    confirmDelete.open = false;
    confirmDelete.agent = null;
  }
  // 실패 시는 error 메시지가 useAgents.error 에 채워지고, 페이지 상단에 표시됨.
}

onMounted(async () => {
  // 우선 helper 가 가리키는 중앙서버가 현재 페이지와 일치하는지 확인 — 다르면 setup 모달
  // 이 최우선 노출. (me) 워크스페이스 모달은 setup 마친 다음 단계.
  await checkHelperSetup();
  if (helperSetupOpen.value) return;
  await fetchAgents();
  await loadMeWorkspace();
  // SSE (agent.changed) 가 주 — polling 은 SSE 끊긴 동안 60s fallback.
  startPolling(60_000);
});
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
.view-toggle {
  display: flex; justify-content: flex-end; gap: 4px;
  margin-bottom: 12px;
}
.toggle-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  background: #fff; border: 1px solid #D4DCE4; border-radius: 4px;
  font-size: 12px; color: #64748B; cursor: pointer;
  transition: background .12s, color .12s, border-color .12s;
}
.toggle-btn:hover { background: #F8FAFC; }
.toggle-btn.active {
  background: #0062FF; color: #fff; border-color: #0062FF;
}
</style>
