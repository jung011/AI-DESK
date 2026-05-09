<template>
  <div class="page_content">
    <div class="group_pageLocation">
      <h2 class="tit_h2">실행 로그</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>실행 로그</em></a>
      </div>
    </div>

    <!-- 필터 -->
    <div class="filter-bar">
      <div class="filter-tabs">
        <button
          v-for="tab in statusTabs"
          :key="tab.value"
          type="button"
          class="filter-tab"
          :class="{ active: filterStatus === tab.value }"
          @click="filterStatus = tab.value">
          {{ tab.label }}
        </button>
      </div>
      <div class="filter-right">
        <select v-model="filterFromAgentId" class="agent-select">
          <option value="">발신자 (전체)</option>
          <option v-for="a in allAgents" :key="a.agentId" :value="a.agentId">
            {{ a.agentName }}
          </option>
        </select>
        <select v-model="filterToAgentId" class="agent-select">
          <option value="">수신자 (전체)</option>
          <option v-for="a in allAgents" :key="a.agentId" :value="a.agentId">
            {{ a.agentName }}
          </option>
        </select>
        <div class="search-input-wrap">
          <svg class="search-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
          <input v-model="filterQuery" type="text" placeholder="본문 검색…" />
        </div>
      </div>
    </div>

    <!-- 결과 테이블 -->
    <div class="audit-table">
      <div class="audit-row audit-head">
        <div class="col-time">시각</div>
        <div class="col-from">발신</div>
        <div class="col-to">수신</div>
        <div class="col-status">상태</div>
        <div class="col-content">본문</div>
        <div class="col-reason">실패 사유</div>
      </div>
      <p v-if="loading" class="audit-empty">불러오는 중…</p>
      <p v-else-if="error" class="audit-empty error">{{ error }}</p>
      <p v-else-if="rows.length === 0" class="audit-empty">조건에 맞는 메시지가 없습니다.</p>
      <div v-else>
        <div v-for="m in rows" :key="m.messageId" class="audit-row">
          <div class="col-time">{{ formatDateTime(m.createdAt) }}</div>
          <div class="col-from">{{ m.fromAgentName }}</div>
          <div class="col-to">{{ m.toAgentName }}</div>
          <div class="col-status"><span class="status-pill" :class="m.status">{{ statusLabel(m.status) }}</span></div>
          <div class="col-content" :title="m.content">{{ truncate(m.content, 80) }}</div>
          <div class="col-reason">{{ m.errorReason ?? '' }}</div>
        </div>
        <p v-if="hasMore" class="audit-more-hint">상위 {{ rows.length }}건만 표시됩니다 — 필터를 좁히세요.</p>
      </div>
    </div>

    <p class="placeholder-note">
      향후 Claude Code CLI 세션 로그 + JSONL 컨텍스트 분석 + 정책 거절 audit 등이 본 페이지에 통합됩니다.
    </p>
  </div>
</template>

<script setup lang="ts">
import type {
  AgentItem,
  AgentListResponse,
  ApiEnvelope
} from '~/vo/agents/AgentVo';
import type {
  MessageItem,
  MessageListResponse,
  MessageStatus
} from '~/vo/messages/MessageVo';

const { $api } = useNuxtApp();

const statusTabs = [
  { label: '전체',   value: '' },
  { label: '발송',   value: 'sent' },
  { label: '전달',   value: 'delivered' },
  { label: '답변됨', value: 'replied' },
  { label: '실패',   value: 'failed' }
] as const;

const allAgents = ref<AgentItem[]>([]);
const filterStatus = ref<'' | MessageStatus>('');
const filterFromAgentId = ref('');
const filterToAgentId = ref('');
const filterQuery = ref('');
const rows = ref<MessageItem[]>([]);
const hasMore = ref(false);
const loading = ref(false);
const error = ref<string | null>(null);

let queryDebounce: ReturnType<typeof setTimeout> | null = null;

async function loadAgents(): Promise<void> {
  const env = await $api<ApiEnvelope<AgentListResponse>>('/api/agents');
  allAgents.value = env.data.list ?? [];
}

async function fetchAudit(): Promise<void> {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filterStatus.value) params.status = filterStatus.value;
    if (filterFromAgentId.value) params.fromAgentId = filterFromAgentId.value;
    if (filterToAgentId.value) params.toAgentId = filterToAgentId.value;
    if (filterQuery.value.trim()) params.q = filterQuery.value.trim();
    params.limit = '200';
    const env = await $api<ApiEnvelope<MessageListResponse>>('/api/messages/audit', { params });
    rows.value = env.data.list ?? [];
    hasMore.value = !!env.data.hasMore;
    error.value = null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

function scheduleFetch(): void {
  if (queryDebounce !== null) clearTimeout(queryDebounce);
  queryDebounce = setTimeout(() => void fetchAudit(), 250);
}

watch([filterStatus, filterFromAgentId, filterToAgentId], () => void fetchAudit());
watch(filterQuery, scheduleFetch);

onMounted(async () => {
  await loadAgents();
  await fetchAudit();
});
onUnmounted(() => {
  if (queryDebounce !== null) clearTimeout(queryDebounce);
});

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  const yy = String(d.getFullYear()).slice(2);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const HH = String(d.getHours()).padStart(2, '0');
  const MM = String(d.getMinutes()).padStart(2, '0');
  const SS = String(d.getSeconds()).padStart(2, '0');
  return `${yy}-${mm}-${dd} ${HH}:${MM}:${SS}`;
}
function truncate(s: string, n: number): string {
  if (!s) return '';
  return s.length > n ? s.slice(0, n) + '…' : s;
}
function statusLabel(s: string): string {
  return ({ sent: '발송', delivered: '전달', replied: '답변됨', failed: '실패' } as Record<string, string>)[s] ?? s;
}
</script>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1500px;
  margin: 0 auto;
}
.group_pageLocation {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px;
}
.tit_h2 { font-size: 20px; font-weight: 700; color: #101010; margin: 0; }
.descList_pageLocation { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #94A3B8; }
.descList_pageLocation a { color: #94A3B8; text-decoration: none; }
.descList_pageLocation a + a::before { content: '›'; margin-right: 6px; color: #CBD5E1; }
.descList_pageLocation em { font-style: normal; color: #475569; font-weight: 600; }

.filter-bar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; margin-bottom: 16px; flex-wrap: wrap;
}
.filter-tabs { display: flex; gap: 4px; }
.filter-tab {
  height: 32px; padding: 0 12px; border-radius: 16px;
  font-size: 12px; font-weight: 500; color: #666;
  border: 1px solid transparent; background: transparent; cursor: pointer;
}
.filter-tab:hover { background: #F1F5F9; }
.filter-tab.active { background: #0062ff; color: #fff; border-color: #0062ff; }

.filter-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.agent-select {
  height: 32px; padding: 0 10px; border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 12px; color: #333; background: #fff;
}
.agent-select:focus { outline: none; border-color: #0062ff; }

.search-input-wrap { position: relative; }
.search-input-wrap input[type="text"] {
  height: 32px; width: 200px; padding: 0 12px 0 30px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 12px; color: #333; background: #fff;
}
.search-input-wrap input[type="text"]:focus { outline: none; border-color: #0062ff; }
.search-icon {
  position: absolute; left: 9px; top: 50%; transform: translateY(-50%);
  width: 13px; height: 13px; color: #999;
}

.audit-table {
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .08);
  overflow: hidden;
}
.audit-row {
  display: grid;
  grid-template-columns: 130px 110px 110px 80px 1fr 200px;
  gap: 12px;
  padding: 8px 14px; border-bottom: 1px solid #F0F2F5;
  font-size: 12px; color: #333; align-items: center;
}
.audit-row:last-child { border-bottom: none; }
.audit-head {
  background: #FAFBFD; font-weight: 600; color: #475569;
  font-size: 11px; letter-spacing: .04em; text-transform: uppercase;
}
.col-content { color: #555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-reason { color: #B22B45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-time { color: #94A3B8; font-variant-numeric: tabular-nums; }

.status-pill {
  display: inline-flex; align-items: center;
  padding: 2px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 600;
}
.status-pill.sent      { background: #F1F5F9; color: #64748B; }
.status-pill.delivered { background: #E0EBFF; color: #0062ff; }
.status-pill.replied   { background: #E8F5E9; color: #2E7D32; }
.status-pill.failed    { background: #FFE5E9; color: #B22B45; }

.audit-empty { padding: 28px 14px; text-align: center; color: #94A3B8; font-size: 13px; }
.audit-empty.error { color: #B22B45; }
.audit-more-hint { padding: 10px 14px; text-align: center; color: #94A3B8; font-size: 12px; }

.placeholder-note {
  margin-top: 16px;
  font-size: 11px; color: #AAB4BE;
}
</style>
