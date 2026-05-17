<template>
  <section class="conv-view">
    <header v-if="partner" class="conv-head">
      <button v-if="showBack" class="cv-back" @click="$emit('back')" aria-label="뒤로">←</button>
      <span class="cv-avatar">{{ avatar(partner.status) }}</span>
      <div class="cv-title">
        <div class="cv-name">{{ partner.agentName }}</div>
        <div class="cv-meta">{{ statusLabel(partner.status) }} · {{ shortModel(partner.model) }}</div>
      </div>
    </header>
    <header v-else class="conv-head empty">
      <span class="cv-placeholder">대화할 AI 를 왼쪽에서 선택하세요</span>
    </header>

    <div v-if="partner" class="conv-body" ref="bodyRef">
      <div v-if="loading && messages.length === 0" class="cv-empty">로딩 중…</div>
      <div v-else-if="messages.length === 0" class="cv-empty">아직 메시지 없음 — 첫 대화를 시작해보세요</div>
      <ul v-else class="cv-msgs">
        <li
          v-for="m in messages"
          :key="m.messageId"
          class="cv-msg"
          :class="{ mine: m.fromAgentId === meId, theirs: m.fromAgentId !== meId }">
          <div class="cv-bubble">
            <div class="cv-content">{{ m.content }}</div>
            <div class="cv-foot">
              <span class="cv-time">{{ formatTime(m.createdAt) }}</span>
              <span
                v-if="m.fromAgentId === meId"
                class="cv-status"
                :class="m.status"
                :title="m.errorReason || ''">
                {{ statusBadge(m.status) }}
              </span>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <footer v-if="partner" class="conv-input">
      <textarea
        v-model="draft"
        class="cv-textarea"
        rows="2"
        :placeholder="`${partner.agentName} 에게 메시지…`"
        :disabled="sending"
        @keydown.enter.exact.prevent="onSend"
      />
      <button
        class="cv-send"
        :disabled="!draft.trim() || sending"
        @click="onSend">
        {{ sending ? '전송 중…' : '전송' }}
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import type { AgentItem, AgentStatus } from '~/vo/agents/AgentVo';
import type { MessageItem } from '~/vo/messages/MessageVo';

const props = defineProps<{
  partner: AgentItem | null;
  messages: MessageItem[];
  meId: string;
  loading: boolean;
  sending: boolean;
  showBack: boolean;
}>();

const emit = defineEmits<{
  (e: 'send', content: string): void;
  (e: 'back'): void;
}>();

const draft = ref('');
const bodyRef = ref<HTMLElement | null>(null);

async function onSend(): Promise<void> {
  const text = draft.value.trim();
  if (!text) return;
  emit('send', text);
  draft.value = '';
  await nextTick();
  scrollToBottom();
}

function scrollToBottom(): void {
  if (!bodyRef.value) return;
  bodyRef.value.scrollTop = bodyRef.value.scrollHeight;
}

watch(() => props.messages.length, () => {
  void nextTick().then(scrollToBottom);
});

function statusLabel(s: AgentStatus): string {
  return { active: '작업중', waiting: '응답 대기', idle: '대기중', error: '오류' }[s] ?? s;
}
function avatar(s: AgentStatus): string {
  return { active: '🤖', waiting: '🙋', idle: '📝', error: '⚠️' }[s] ?? '📝';
}
function shortModel(m: string | null | undefined): string {
  if (!m) return '';
  return m.toLowerCase().startsWith('claude') ? 'claude' : m;
}

function statusBadge(status: string): string {
  return { sent: '⏳', delivered: '✓', replied: '✓✓', failed: '⚠' }[status] ?? '';
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}
</script>

<style scoped>
.conv-view { display: flex; flex-direction: column; background: #F8FAFC; min-width: 0; }

.conv-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; background: #fff;
  border-bottom: 1px solid #E5E9EF;
  flex-shrink: 0;
}
.conv-head.empty { justify-content: center; color: #94A3B8; }
.cv-placeholder { font-size: 13px; }
.cv-back {
  display: none; padding: 6px 10px;
  background: transparent; border: none; cursor: pointer;
  font-size: 18px; color: #475569;
}
.cv-avatar {
  width: 36px; height: 36px; border-radius: 8px;
  background: #F1F5F9;
  display: flex; align-items: center; justify-content: center; font-size: 16px;
}
.cv-title { display: flex; flex-direction: column; gap: 2px; }
.cv-name { font-size: 14px; font-weight: 700; color: #101010; }
.cv-meta { font-size: 11px; color: #64748B; }

.conv-body { flex: 1; overflow-y: auto; padding: 16px 18px; }
.cv-empty { color: #94A3B8; font-size: 13px; text-align: center; margin-top: 40px; }

.cv-msgs { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.cv-msg { display: flex; }
.cv-msg.mine { justify-content: flex-end; }
.cv-msg.theirs { justify-content: flex-start; }

.cv-bubble {
  max-width: 75%; padding: 9px 13px; border-radius: 14px;
  background: #fff; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
  word-break: break-word; white-space: pre-wrap;
}
.cv-msg.mine .cv-bubble { background: #DBEAFE; color: #1E3A8A; }
.cv-msg.theirs .cv-bubble { background: #fff; color: #101010; border: 1px solid #E5E9EF; }
.cv-content { font-size: 14px; line-height: 1.5; }
.cv-foot { display: flex; gap: 6px; align-items: center; margin-top: 4px; font-size: 10px; color: #64748B; }
.cv-status.sent     { color: #94A3B8; }
.cv-status.delivered{ color: #2E7D32; }
.cv-status.replied  { color: #2E7D32; font-weight: 700; }
.cv-status.failed   { color: #B71C1C; font-weight: 700; }

.conv-input {
  display: flex; gap: 10px; align-items: flex-end;
  padding: 12px 14px; background: #fff;
  border-top: 1px solid #E5E9EF;
  flex-shrink: 0;
}
.cv-textarea {
  flex: 1; resize: none; padding: 8px 12px;
  font-size: 14px; line-height: 1.5; font-family: inherit;
  border: 1px solid #D4DCE4; border-radius: 8px;
  background: #F8FAFC; color: #101010;
}
.cv-textarea:focus { outline: none; border-color: #3B5BDB; background: #fff; }
.cv-textarea:disabled { background: #F1F5F9; }
.cv-send {
  padding: 10px 20px; font-size: 14px; font-weight: 600;
  background: #3B5BDB; color: #fff; border: none; border-radius: 8px;
  cursor: pointer;
}
.cv-send:disabled { background: #CBD5E1; cursor: not-allowed; }

/* 모바일 */
@media (max-width: 768px) {
  .cv-back { display: block; }
}
</style>
