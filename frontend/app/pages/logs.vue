<template>
  <div class="page_content">
    <div class="group_pageLocation">
      <h2 class="tit_h2">로그</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>로그</em></a>
      </div>
    </div>

    <section class="card">
      <header class="card-head">
        <h3 class="card-title">AI 간 변경 활동</h3>
        <p class="card-desc">
          코드/스키마/파일을 만들거나 수정하거나 삭제하는 AI 간 대화와 실제 실행된 mutation 액션을 통합 피드로 보여줍니다.
        </p>
      </header>

      <div class="filter-bar">
        <button
          v-for="t in tabs" :key="t.value"
          type="button"
          class="tab"
          :class="{ active: category === t.value }"
          @click="onTab(t.value)">
          {{ t.label }}
        </button>
        <span class="filter-spacer" />
        <button type="button" class="refresh-btn" :disabled="loading" @click="fetchOnce">
          {{ loading ? '갱신 중…' : '↻ 새로고침' }}
        </button>
      </div>

      <div v-if="loading && items.length === 0" class="state-msg">로딩 중…</div>
      <div v-else-if="!loading && items.length === 0" class="state-msg">조건에 맞는 로그가 없습니다.</div>

      <ul v-else class="feed">
        <li v-for="(it, idx) in items" :key="rowKey(it, idx)" class="row" :class="`row-${it.type}`">
          <div class="row-head">
            <span class="badge" :class="`cat-${it.category}`">{{ categoryLabel(it.category) }}</span>
            <span class="row-type">{{ it.type === 'message' ? '💬' : '⚙️' }}</span>
            <span class="row-actor">
              <strong>{{ it.agentName || '(unknown)' }}</strong>
              <template v-if="it.type === 'message' && it.toAgentName">
                <span class="arrow">→</span><strong>{{ it.toAgentName }}</strong>
              </template>
            </span>
            <span class="row-time">{{ formatTime(it.createdAt) }}</span>
          </div>
          <div class="row-body">
            <template v-if="it.type === 'message'">
              <p class="content">{{ truncate(it.content, 400) }}</p>
              <p v-if="it.messageStatus === 'failed' && it.errorReason" class="err-line">
                ⚠️ 전달 실패: {{ it.errorReason }}
              </p>
            </template>
            <template v-else>
              <p class="tool-line">
                <code class="tool-name">{{ it.tool }}</code>
                <span v-if="it.target" class="tool-target">{{ truncate(it.target, 200) }}</span>
              </p>
              <p v-if="it.summary && it.summary !== it.target" class="summary">{{ truncate(it.summary, 200) }}</p>
            </template>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface FeedItem {
  type: 'message' | 'action';
  createdAt: string;
  category: string;
  agentId?: string;
  agentName?: string;
  // message
  messageId?: string;
  toAgentId?: string;
  toAgentName?: string;
  content?: string;
  messageStatus?: string;
  errorReason?: string;
  // action
  logId?: string;
  tool?: string;
  target?: string;
  summary?: string;
  sessionId?: string;
}

const tabs = [
  { label: '전체',     value: '' },
  { label: '오류',     value: 'error' },
  { label: '코드',     value: 'code' },
  { label: '스키마',   value: 'schema' },
  { label: '파일',     value: 'file' },
  { label: '명령',     value: 'command' },
  { label: '대화',     value: 'discussion' },
] as const;

const items = ref<FeedItem[]>([]);
const category = ref<string>('');
const loading = ref(false);
let timer: ReturnType<typeof setInterval> | null = null;

async function fetchOnce(): Promise<void> {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const q = new URLSearchParams();
    if (category.value) q.set('category', category.value);
    q.set('limit', '150');
    const env = await $api<ApiEnvelope<FeedItem[]>>(`/api/logs?${q.toString()}`);
    if (env.result === 0 && Array.isArray(env.data)) {
      items.value = env.data;
    }
  } catch {
    /* swallow — 다음 폴링에서 재시도 */
  } finally {
    loading.value = false;
  }
}

function onTab(v: string): void {
  if (category.value === v) return;
  category.value = v;
  void fetchOnce();
}

function rowKey(it: FeedItem, idx: number): string {
  return (it.messageId || it.logId || `${it.type}-${idx}`) + '-' + idx;
}

function truncate(s: string | undefined, n: number): string {
  if (!s) return '';
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function categoryLabel(c: string): string {
  return ({
    code: '코드',
    schema: '스키마',
    file: '파일',
    command: '명령',
    discussion: '대화',
    error: '오류',
  } as Record<string, string>)[c] ?? c;
}

function formatTime(iso: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${dd} ${hh}:${mm}`;
  } catch {
    return iso.slice(0, 16);
  }
}

onMounted(() => {
  void fetchOnce();
  timer = setInterval(fetchOnce, 30_000);
});
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}
.group_pageLocation {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px;
}
.tit_h2 { font-size: 20px; font-weight: 700; color: #101010; margin: 0; }
.descList_pageLocation {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #94A3B8;
}
.descList_pageLocation a { color: #94A3B8; text-decoration: none; }
.descList_pageLocation a + a::before {
  content: '›'; margin-right: 6px; color: #CBD5E1;
}
.descList_pageLocation em { font-style: normal; color: #475569; font-weight: 600; }

.card {
  background: var(--bg-card); border: 1px solid #E2E8F0; border-radius: 8px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .08);
  margin-bottom: 20px;
}
.card-head {
  padding: 18px 22px;
  border-bottom: 1px solid #F0F2F5;
}
.card-title { font-size: 15px; font-weight: 700; color: #101010; margin: 0 0 6px; }
.card-desc { font-size: 12px; color: #94A3B8; margin: 0; line-height: 1.6; }

.filter-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 22px; border-bottom: 1px solid #F0F2F5;
}
.tab {
  height: 30px; padding: 0 14px;
  background: var(--bg-card); color: #475569;
  border: 1px solid #D4DCE4; border-radius: 16px;
  font-size: 12px; font-weight: 600; cursor: pointer;
}
.tab:hover:not(.active) { background: #F8FAFC; border-color: #0062ff; color: #0062ff; }
.tab.active { background: #0062ff; border-color: #0062ff; color: #fff; }
.filter-spacer { flex: 1; }
.refresh-btn {
  height: 30px; padding: 0 12px;
  background: #F8FAFC; color: #475569;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 12px; cursor: pointer;
}
.refresh-btn:disabled { opacity: .6; cursor: not-allowed; }

.state-msg {
  padding: 60px 22px; text-align: center;
  color: #94A3B8; font-size: 13px;
}

.feed { list-style: none; padding: 0; margin: 0; }
.row {
  padding: 14px 22px;
  border-bottom: 1px solid #F0F2F5;
  display: flex; flex-direction: column; gap: 8px;
}
.row:last-child { border-bottom: none; }
.row-action { background: #FAFBFE; }

.row-head {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: #475569;
}
.badge {
  display: inline-flex; align-items: center;
  height: 22px; padding: 0 9px; border-radius: 11px;
  font-size: 11px; font-weight: 700;
  background: #EEF2FF; color: #4338CA;
}
.badge.cat-code       { background: #DBEAFE; color: #1E40AF; }
.badge.cat-schema     { background: #FFF8E1; color: #92400E; }
.badge.cat-file       { background: #E8F5E9; color: #2E7D32; }
.badge.cat-command    { background: #F3E8FF; color: #6A1B9A; }
.badge.cat-discussion { background: #F1F5F9; color: #64748B; }
.badge.cat-error      { background: #FFEBEE; color: #B71C1C; }

.row-type { font-size: 14px; }
.row-actor strong { color: #101010; font-weight: 600; }
.row-actor .arrow { margin: 0 6px; color: #94A3B8; }
.row-time { margin-left: auto; color: #94A3B8; font-size: 11px; }

.row-body { font-size: 13px; color: #1E293B; line-height: 1.6; }
.row-body .content {
  margin: 0; white-space: pre-wrap; word-break: break-word;
}
.row-body .tool-line {
  margin: 0; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
}
.row-body .tool-name {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px; padding: 2px 6px; border-radius: 4px;
  background: #F1F5F9; color: #475569;
}
.row-body .tool-target {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px; color: #475569; word-break: break-all;
}
.row-body .summary { margin: 4px 0 0; color: #475569; font-size: 12px; }
.row-body .err-line {
  margin: 6px 0 0; padding: 6px 10px;
  background: #FFEBEE; border-left: 3px solid #E53935;
  border-radius: 4px;
  color: #B71C1C; font-size: 12px; font-weight: 500;
}
</style>
