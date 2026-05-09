<template>
  <div class="page_content">
    <!-- 페이지 헤더 -->
    <div class="group_pageLocation">
      <h2 class="tit_h2">메시지</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>메시지</em></a>
      </div>
      <div style="margin-left: auto;">
        <button type="button" class="btn normal type_v1" @click="newMsgOpen = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:6px"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" /></svg>
          새 메시지
        </button>
      </div>
    </div>

    <!-- 메시지 본문 — 좌 320 + 우 타임라인 -->
    <div class="messages-wrap">

      <!-- 좌측 — 관점 AI 선택 + 대화 목록 -->
      <aside class="conv-list">
        <div class="conv-list-header">
          <label class="me-label">관점 AI</label>
          <select class="me-select" :value="me.meAgentId ?? ''" @change="onMeChange">
            <option value="">선택하세요…</option>
            <option v-for="a in selectableAgents" :key="a.agentId" :value="a.agentId">
              {{ a.agentName }} ({{ statusLabel(a.status) }})
            </option>
          </select>
        </div>

        <div class="conv-list-body">
          <p v-if="!me.meAgentId" class="conv-hint">
            관점이 될 AI 를 선택하면 그 AI 가 참여한 대화가 보입니다.
          </p>
          <p v-else-if="me.conversations.length === 0" class="conv-hint">
            아직 대화가 없습니다.
          </p>
          <div
            v-for="c in me.conversations"
            :key="c.partnerAgentId"
            class="conv-item"
            :class="{ active: me.selectedPartnerId === c.partnerAgentId }"
            @click="me.selectConversation(c.partnerAgentId)">
            <div class="conv-avatar" :class="avatarClass(c.partnerStatus)">{{ avatarEmoji(c.partnerStatus) }}</div>
            <div class="conv-info">
              <div class="conv-name-row">
                <span class="conv-name">
                  {{ c.partnerAgentName }}
                  <span v-if="c.unreadCount > 0" class="unread-count">{{ c.unreadCount }}</span>
                </span>
                <span class="conv-time">{{ relativeTime(c.lastActivityAt) }}</span>
              </div>
              <div class="conv-preview">
                <span v-if="c.lastDirection === 'outbox'" class="conv-preview-prefix">나 →</span>
                {{ c.lastMessageContent }}
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 우측 — 대화 헤더 + 타임라인 + 컴포저 -->
      <section class="conv-detail">
        <template v-if="me.selectedConversation">
          <div class="conv-detail-header">
            <div class="conv-avatar" :class="avatarClass(me.selectedConversation.partnerStatus)" style="width:36px;height:36px;font-size:18px">
              {{ avatarEmoji(me.selectedConversation.partnerStatus) }}
            </div>
            <div>
              <div class="conv-detail-title">{{ me.selectedConversation.partnerAgentName }}</div>
              <div class="conv-detail-sub">
                {{ statusLabel(me.selectedConversation.partnerStatus) }}
                <span>·</span>
                <span>{{ me.selectedConversation.partnerWorkspaceDir }}</span>
              </div>
            </div>
          </div>

          <div ref="timelineEl" class="conv-timeline">
            <p v-if="me.messages.length === 0" class="conv-hint">메시지가 없습니다.</p>
            <MessageBubble
              v-for="m in me.messages"
              :key="m.messageId"
              :message="m"
              :outgoing="m.fromAgentId === me.meAgentId" />
          </div>

          <div class="composer">
            <textarea
              v-model="composerText"
              :maxlength="1000"
              placeholder="메시지를 입력하세요... (Shift+Enter 줄바꿈, Enter 전송)"
              :disabled="sending"
              @keydown.enter.exact.prevent="onSend"
              @keydown.enter.shift.exact="" />
            <span class="composer-counter">{{ composerText.length }} / 1000</span>
            <button
              type="button"
              class="btn normal type_v1"
              :disabled="!canSend || sending"
              @click="onSend">
              {{ sending ? '보내는 중…' : '보내기' }}
            </button>
          </div>
        </template>

        <div v-else class="conv-detail-empty">
          <p>좌측에서 대화를 선택하면 메시지가 여기에 표시됩니다.</p>
        </div>
      </section>

    </div>

    <!-- 새 메시지 팝업 -->
    <NewMessageDialog
      :open="newMsgOpen"
      :agents="allAgents"
      :initial-from-agent-id="me.meAgentId"
      :submitting="newMsgSubmitting"
      :error-message="newMsgError"
      @close="closeNewMsg"
      @submit="onSendNewMessage" />
  </div>
</template>

<script setup lang="ts">
import { useMessagesStore } from '~/stores/messages';
import MessageBubble from '~/components/messages/MessageBubble.vue';
import NewMessageDialog from '~/components/messages/NewMessageDialog.vue';
import type { AgentItem, AgentListResponse, ApiEnvelope, AgentStatus } from '~/vo/agents/AgentVo';
import type { MessageCreateRequest } from '~/vo/messages/MessageVo';

const me = useMessagesStore();
const route = useRoute();
const { $api } = useNuxtApp();

const allAgents = ref<AgentItem[]>([]);
const composerText = ref('');
const sending = ref(false);
const timelineEl = ref<HTMLElement | null>(null);

// 새 메시지 팝업
const newMsgOpen = ref(false);
const newMsgSubmitting = ref(false);
const newMsgError = ref<string | null>(null);

function closeNewMsg(): void {
  if (newMsgSubmitting.value) return;
  newMsgOpen.value = false;
  newMsgError.value = null;
}

async function onSendNewMessage(req: MessageCreateRequest): Promise<void> {
  newMsgSubmitting.value = true;
  newMsgError.value = null;
  const result = await me.sendNewMessage(req);
  newMsgSubmitting.value = false;
  if (result) {
    newMsgOpen.value = false;
    // 발신 후 해당 대화로 자동 진입 (관점 AI 가 발신자라면)
    if (me.meAgentId === req.fromAgentId) {
      await me.selectConversation(req.toAgentId);
    }
  } else {
    newMsgError.value = me.error ?? '발신 실패';
  }
}

const selectableAgents = computed(() =>
  allAgents.value.filter(a => a.status === 'active' || a.status === 'idle')
);

const canSend = computed(() =>
  Boolean(me.meAgentId) &&
  Boolean(me.selectedPartnerId) &&
  composerText.value.trim().length > 0
);

async function loadAgents(): Promise<void> {
  const env = await $api<ApiEnvelope<AgentListResponse>>('/api/agents');
  allAgents.value = env.data.list ?? [];
}

async function onMeChange(e: Event): Promise<void> {
  const v = (e.target as HTMLSelectElement).value || null;
  await me.setMe(v);
  // 만약 ?withId 가 쿼리에 있으면 해당 대화로 진입 시도
  await maybeApplyWithIdFromQuery();
  await me.fetchUnreadCount();
}

async function onSend(): Promise<void> {
  if (!canSend.value || sending.value) return;
  sending.value = true;
  const text = composerText.value.trim();
  composerText.value = '';
  await me.sendMessage(text);
  sending.value = false;
  await nextTick();
  scrollTimelineToBottom();
}

async function maybeApplyWithIdFromQuery(): Promise<void> {
  const wid = (route.query.withId as string | undefined) ?? null;
  if (wid && me.conversations.find(c => c.partnerAgentId === wid)) {
    await me.selectConversation(wid);
  }
}

function scrollTimelineToBottom(): void {
  const el = timelineEl.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function avatarClass(status: string): string {
  if (status === 'active') return 'working';
  if (status === 'idle')   return 'idle';
  return 'done';
}
function avatarEmoji(status: string): string {
  if (status === 'active') return '🤖';
  if (status === 'idle')   return '📝';
  return '✅';
}
function statusLabel(status: string | AgentStatus): string {
  if (status === 'active') return '작업중';
  if (status === 'idle')   return '쉬는 중';
  return '완료';
}
function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1) return '방금';
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.floor(h / 24)}일 전`;
}

// 진입/이탈
let pollHandle: ReturnType<typeof setInterval> | null = null;
onMounted(async () => {
  await loadAgents();
  await me.fetchUnreadCount();
  // 사용자가 관점 AI 를 선택하면 그 다음에 conversations 가 fetch 된다.
  pollHandle = setInterval(() => {
    void me.fetchConversations();
    if (me.selectedPartnerId) void me.fetchMessages();
    void me.fetchUnreadCount();
  }, 10_000);
});
onUnmounted(() => {
  if (pollHandle !== null) clearInterval(pollHandle);
});

// 대화 변경 후 자동 스크롤
watch(() => me.messages.length, async () => {
  await nextTick();
  scrollTimelineToBottom();
});
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

.messages-wrap {
  display: grid; grid-template-columns: 320px 1fr; gap: 16px;
  height: calc(100vh - 240px); min-height: 540px;
}

/* 좌측 - 대화 목록 */
.conv-list {
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .12);
  display: flex; flex-direction: column; overflow: hidden;
}
.conv-list-header {
  padding: 12px 14px; border-bottom: 1px solid #F0F2F5;
  background: #FAFBFD;
  display: flex; flex-direction: column; gap: 6px;
}
.me-label {
  font-size: 11px; font-weight: 600; color: #475569;
  letter-spacing: .04em;
}
.me-select {
  height: 34px; padding: 0 10px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; color: #333; background: #fff;
  width: 100%;
}
.me-select:focus { outline: none; border-color: #0062ff; }

.conv-list-body { flex: 1; overflow-y: auto; }
.conv-hint {
  padding: 28px 18px;
  font-size: 12px; color: #94A3B8;
  text-align: center; line-height: 1.6;
}
.conv-item {
  padding: 12px 14px; border-bottom: 1px solid #F0F2F5; cursor: pointer;
  transition: background .15s;
  display: flex; align-items: flex-start; gap: 10px;
}
.conv-item:hover { background: #F8FAFC; }
.conv-item.active {
  background: #EEF2FF; border-left: 3px solid #0062ff; padding-left: 11px;
}
.conv-avatar {
  width: 32px; height: 32px; border-radius: 6px; background: #F1F5F9;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; flex-shrink: 0;
}
.conv-avatar.working { background: #E8F5E9; }
.conv-avatar.idle    { background: #FFF8E1; }
.conv-avatar.done    { background: #F3E8FF; }
.conv-info { flex: 1; min-width: 0; }
.conv-name-row {
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
}
.conv-name { font-size: 13px; font-weight: 600; color: #101010; }
.conv-time { font-size: 11px; color: #AAB4BE; flex-shrink: 0; }
.conv-preview {
  font-size: 12px; color: #666; margin-top: 3px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.conv-preview-prefix {
  color: #94A3B8; font-weight: 500; margin-right: 4px;
}
.unread-count {
  min-width: 18px; padding: 0 5px; height: 18px; border-radius: 9px;
  background: #E53935; color: #fff; font-size: 10px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
  margin-left: 6px;
}

/* 우측 - 타임라인 */
.conv-detail {
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .12);
  display: flex; flex-direction: column; overflow: hidden;
}
.conv-detail-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: #94A3B8; font-size: 13px;
}
.conv-detail-header {
  padding: 14px 18px; border-bottom: 1px solid #F0F2F5;
  display: flex; align-items: center; gap: 12px; background: #FAFBFD;
}
.conv-detail-title { font-size: 14px; font-weight: 700; color: #101010; }
.conv-detail-sub {
  font-size: 11px; color: #666; margin-top: 2px;
  display: flex; align-items: center; gap: 8px;
}
.conv-timeline { flex: 1; overflow-y: auto; padding: 18px; background: #FAFBFD; }

.composer {
  border-top: 1px solid #F0F2F5; padding: 12px 14px;
  display: flex; gap: 8px; align-items: flex-end; background: #fff;
}
.composer textarea {
  flex: 1; min-height: 40px; max-height: 120px;
  padding: 10px 12px; border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; resize: none; font-family: inherit;
}
.composer textarea:focus { outline: none; border-color: #0062ff; }
.composer-counter {
  font-size: 11px; color: #AAB4BE; margin-right: 4px; align-self: center;
}
.btn.normal { display: inline-flex; align-items: center; height: 40px; padding: 0 18px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; border: 1px solid transparent; }
.btn.normal.type_v1 { background: #0062ff; color: #fff; }
.btn.normal.type_v1:hover:not(:disabled) { background: #0052d4; }
.btn.normal.type_v1:disabled { background: #94A3B8; cursor: not-allowed; }
</style>
