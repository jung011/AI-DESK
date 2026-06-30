<template>
  <section class="colleague-section">
    <div class="colleague-head">
      <h3 class="colleague-title">사내 동료 AI</h3>
      <div class="colleague-head-right">
        <span class="colleague-summary">
          <span class="online-dot online" /> 온라인 {{ onlineCount }}
          <span class="colleague-sep">·</span>
          전체 {{ colleagues.list.value.length }}
        </span>
        <button class="ext-add-btn" @click="dialogOpen = true">+ 외부 AI</button>
      </div>
    </div>

    <ExternalAgentDialog v-model="dialogOpen" @created="onExternalCreated" />
    <ExternalAgentRotateDialog
      v-if="rotateTarget"
      v-model="rotateOpen"
      :agent-id="rotateTarget.agentId"
      :agent-name="rotateTarget.agentName"
      @rotated="onExternalCreated"
    />

    <div v-if="deleteTarget" class="confirm-backdrop" @click.self="closeConfirm">
      <div class="confirm-modal" role="dialog" aria-modal="true">
        <header class="confirm-head">
          <div class="confirm-icon-wrap">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
              <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
            </svg>
          </div>
          <h3>외부 AI 삭제</h3>
        </header>
        <div class="confirm-body">
          <p class="confirm-target">
            <strong>{{ deleteTarget.meAgentName || '(unknown)' }}</strong> 를 삭제할까요?
          </p>
          <ul class="confirm-detail">
            <li>backend agent 행과 메시지 이력 영구 삭제 (복구 불가)</li>
            <li>외부 환경의 daemon / mcp 정리는 외부 사용자 책임</li>
          </ul>
          <div v-if="deleteError" class="confirm-error">{{ deleteError }}</div>
        </div>
        <footer class="confirm-foot">
          <button class="ext-btn" :disabled="deleteBusy" @click="closeConfirm">취소</button>
          <button class="ext-btn danger" :disabled="deleteBusy" @click="confirmDelete">
            {{ deleteBusy ? '삭제 중…' : '삭제' }}
          </button>
        </footer>
      </div>
    </div>

    <div v-if="colleagues.list.value.length === 0" class="colleague-empty">
      가입한 사내 동료가 없습니다.
      <small class="colleague-empty-hint">
        새 동료는 <code>POST /api/auth/signup</code> 으로 가입 후 (me) 워크스페이스 지정 시 여기 표시됩니다.
      </small>
    </div>

    <div v-else class="colleague-grid">
      <div
        v-for="c in sorted"
        :key="c.meAgentId ?? `acc-${c.accountSn}`"
        class="colleague-card"
        :class="{
          offline: !c.online,
          'me-unset': !c.meAgentId,
          'external': c.agentType === 'external',
        }">
        <span class="online-dot" :class="{ online: c.online }" />
        <button
          v-if="c.agentType === 'external'"
          class="ext-action-btn ext-rotate-btn"
          title="외부 AI token rotate — 새 token 발급. 옛 token 은 즉시 무효."
          @click="onRotateExternal(c)"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
               stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
        <button
          v-if="c.agentType === 'external'"
          class="ext-action-btn ext-delete-btn"
          title="외부 AI 삭제 — backend 통신만 차단. 외부 daemon/mcp cleanup 은 사용자 책임."
          @click="onDeleteExternal(c)"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
               stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
            <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
          </svg>
        </button>
        <div class="colleague-name">
          <template v-if="c.agentType === 'external'">
            {{ c.meAgentName }}
            <span class="external-tag">외부 AI</span>
          </template>
          <template v-else>
            {{ c.displayName || c.loginId }}
            <span v-if="!c.meAgentId" class="me-unset-tag">(me) 미지정</span>
          </template>
        </div>
        <div class="colleague-meta">
          <template v-if="c.agentType === 'external'">
            {{ c.loginId }} · {{ c.meStatus || 'offline' }}
          </template>
          <template v-else>
            {{ c.loginId }}
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useColleagues } from '~/composables/useColleagues';
import ExternalAgentDialog from './ExternalAgentDialog.vue';
import ExternalAgentRotateDialog from './ExternalAgentRotateDialog.vue';

const colleagues = useColleagues();
// SSE 가 살아있는 동안 polling 은 *backup* 으로만 — 60s. SSE 끊기면 polling 이 fallback.
const POLL_INTERVAL_MS = 60_000;
let timer: ReturnType<typeof setInterval> | null = null;
let evtSource: EventSource | null = null;
let refreshDebounce: ReturnType<typeof setTimeout> | null = null;

function scheduleRefresh() {
  if (refreshDebounce) return;
  refreshDebounce = setTimeout(() => {
    refreshDebounce = null;
    colleagues.refresh();
  }, 300);
}

const dialogOpen = ref(false);
function onExternalCreated() {
  colleagues.refresh();
}

const rotateOpen = ref(false);
const rotateTarget = ref<{ agentId: string; agentName: string } | null>(null);
function onRotateExternal(c: { meAgentId?: string | null; meAgentName?: string | null }) {
  if (!c.meAgentId) return;
  rotateTarget.value = { agentId: c.meAgentId, agentName: c.meAgentName || '' };
  rotateOpen.value = true;
}

const { $api } = useNuxtApp();
type DeletableExternal = { meAgentId?: string | null; meAgentName?: string | null };
const deleteTarget = ref<DeletableExternal | null>(null);
const deleteBusy = ref(false);
const deleteError = ref<string | null>(null);

function onDeleteExternal(c: DeletableExternal) {
  if (!c.meAgentId) return;
  deleteError.value = null;
  deleteBusy.value = false;
  deleteTarget.value = c;
}

function closeConfirm() {
  if (deleteBusy.value) return;
  deleteTarget.value = null;
}

async function confirmDelete() {
  const t = deleteTarget.value;
  if (!t?.meAgentId) return;
  deleteBusy.value = true;
  deleteError.value = null;
  try {
    await $api(`/api/agents/${encodeURIComponent(t.meAgentId)}`, { method: 'DELETE' });
    deleteTarget.value = null;
    await colleagues.refresh();
  } catch (e) {
    deleteError.value = (e as Error)?.message || String(e);
  } finally {
    deleteBusy.value = false;
  }
}

onMounted(() => {
  colleagues.refresh();
  timer = setInterval(() => colleagues.refresh(), POLL_INTERVAL_MS);
  // SSE — agent.changed 받으면 즉시 refresh (debounce). 끊기면 polling 60s 가 fallback.
  if (typeof window !== 'undefined' && typeof EventSource !== 'undefined') {
    evtSource = new EventSource('/api/messages/events');
    evtSource.addEventListener('agent.changed', () => scheduleRefresh());
  }
});

onBeforeUnmount(() => {
  if (timer != null) clearInterval(timer);
  if (refreshDebounce != null) clearTimeout(refreshDebounce);
  evtSource?.close();
  evtSource = null;
});

const sorted = computed(() => {
  return [...colleagues.list.value].sort((a, b) => {
    // online → me 지정 → loginId
    if (a.online !== b.online) return a.online ? -1 : 1;
    if (!!a.meAgentId !== !!b.meAgentId) return a.meAgentId ? -1 : 1;
    return a.loginId.localeCompare(b.loginId);
  });
});

const onlineCount = computed(() =>
  colleagues.list.value.filter((c) => c.online).length,
);
</script>

<style scoped>
.colleague-section {
  margin-top: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 18px 20px;
  box-shadow: none;
}
.colleague-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.colleague-title { font-size: 15px; font-weight: 700; color: var(--text); }
.colleague-head-right {
  display: flex; align-items: center; gap: 12px;
}
.ext-add-btn {
  font-size: 11px; padding: 6px 14px;
  background: linear-gradient(135deg, #6BB6FF, #B89AFF);
  border: none; border-radius: 6px;
  color: #fff; font-weight: 700; cursor: pointer;
  box-shadow: 0 2px 8px rgba(107, 182, 255, 0.25);
  transition: box-shadow .15s, transform .12s;
}
.ext-add-btn:hover { box-shadow: 0 4px 14px rgba(184, 154, 255, 0.45); transform: translateY(-1px); }
.colleague-summary {
  font-size: 12px; color: var(--text-muted);
  display: inline-flex; align-items: center; gap: 6px;
}
.colleague-sep { color: #CBD5E1; }
.online-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #CBD5E1;
  display: inline-block;
}
.online-dot.online { background: #00d084; }

.colleague-empty {
  padding: 32px 20px; text-align: center;
  color: var(--text-muted); font-size: 13px;
}
.colleague-empty-hint {
  display: block; margin-top: 8px; color: var(--text-dim); font-size: 11px;
}
.colleague-empty-hint code {
  background: rgba(15, 23, 41, 0.4); padding: 1px 4px; border-radius: 3px; font-family: monospace;
}

.colleague-grid {
  display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}
.colleague-card {
  position: relative;
  /* 모든 카드 통일 — 알바 (external) 카드 의 alpha 색. online/offline 차이는 *online-dot* 만 */
  background: rgba(107, 182, 255, 0.08);
  border: 1px solid rgba(107, 182, 255, 0.4);
  border-radius: 6px;
  padding: 12px 14px;
  text-align: left;
  font-family: inherit;
  display: flex; flex-direction: column; gap: 4px;
}
/* offline 카드 도 같은 배경 — 색 통일 (요청 spec) */
.colleague-card.offline { background: rgba(107, 182, 255, 0.08); }
.colleague-card.me-unset { opacity: 0.7; }
.colleague-card .online-dot {
  position: absolute; top: 12px; right: 12px;
}
.colleague-name {
  font-size: 13px; font-weight: 600; color: var(--text);
  padding-right: 16px;     /* online-dot 공간 */
}
.me-unset-tag {
  font-size: 10px; font-weight: 500; color: var(--text-dim);
  margin-left: 4px;
}
.colleague-meta {
  font-size: 11px; color: var(--text-muted);
}

/* 외부 AI 카드 — 옛엔 별 색 박혔는데 사용자 정정으로 모든 카드 통일.
   external-tag 만 *외부 AI* 구분 표시. */
.colleague-card.external {
  /* base .colleague-card 와 동일 — override 안 함 */
}
.colleague-card.external.offline {
  /* base .colleague-card.offline 와 동일 */
}
.external-tag {
  font-size: 10px; font-weight: 600; color: var(--link);
  background: rgba(107, 182, 255, 0.2); padding: 1px 6px; border-radius: 3px;
  margin-left: 6px;
}
.ext-action-btn {
  position: absolute; top: 8px;
  width: 20px; height: 20px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 4px;
  color: var(--text-dim);
  cursor: pointer; opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}
.colleague-card.external:hover .ext-action-btn { opacity: 1; }
.ext-rotate-btn { right: 48px; }
.ext-rotate-btn:hover { color: var(--link); background: rgba(107, 182, 255, 0.2); }
.ext-delete-btn { right: 26px; }
.ext-delete-btn:hover { color: var(--danger); background: rgba(248, 113, 113, 0.18); }

/* Confirm modal — ExternalAgentDialog 와 톤 통일. */
.confirm-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,.42);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
  animation: confirm-fade 0.12s ease-out;
}
@keyframes confirm-fade { from { opacity: 0; } to { opacity: 1; } }
.confirm-modal {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
  width: 420px; max-width: 92vw;
  box-shadow: 0 12px 40px rgba(0,0,0,.55);
  overflow: hidden;
  animation: confirm-pop 0.16s cubic-bezier(.2,.9,.3,1);
}
@keyframes confirm-pop {
  from { transform: translateY(8px) scale(.97); opacity: 0; }
  to   { transform: translateY(0)    scale(1);   opacity: 1; }
}
.confirm-head {
  display: flex; align-items: center; gap: 12px;
  padding: 18px 20px 12px;
}
.confirm-icon-wrap {
  width: 36px; height: 36px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: rgba(248, 113, 113, 0.18); color: #FCA5A5;
  flex-shrink: 0;
}
.confirm-head h3 {
  margin: 0; font-size: 15px; font-weight: 700; color: #FFFFFF;
}
.confirm-body { padding: 4px 20px 18px; }
.confirm-target {
  font-size: 14px; color: #FFFFFF; margin: 0 0 10px;
  line-height: 1.5;
}
.confirm-target strong { color: #93C5FD; }
.confirm-detail {
  margin: 0; padding-left: 18px;
  font-size: 12px; color: #B0BCD0; line-height: 1.6;
}
.confirm-error {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 4px;
  background: rgba(248, 113, 113, 0.15); color: #FCA5A5;
  border: 1px solid rgba(248, 113, 113, 0.35);
  font-size: 12px;
}
.confirm-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 20px 16px;
  border-top: 1px solid var(--border);
}
.ext-btn {
  padding: 7px 16px; border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg-input); cursor: pointer; font-size: 13px;
  color: #E5EBF5;
  font-family: inherit;
}
.ext-btn:hover:not(:disabled) {
  background: rgba(107, 182, 255, 0.1);
  border-color: #6BB6FF;
}
.ext-btn:disabled { cursor: not-allowed; opacity: 0.6; }
.ext-btn.danger {
  background: #E25555; color: #fff; border-color: #E25555;
}
.ext-btn.danger:hover:not(:disabled) {
  background: #CF4444; border-color: #CF4444;
}
</style>
