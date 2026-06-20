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
            <!--
              발신자 이름 라벨 — contact-centric view 에서는 partner 와의 1:1 페어 외에도
              다른 AI 들이 partner 한테 보낸/받은 메시지가 섞이므로 누가 보낸지 명시.
              본인(휴먼) 발신 메시지는 라벨 생략.
            -->
            <div
              v-if="m.fromAgentId !== meId && partner && m.fromAgentId !== partner.agentId"
              class="cv-sender">
              {{ m.fromAgentName }} → {{ m.toAgentName }}
            </div>
            <div
              v-else-if="m.fromAgentId !== meId"
              class="cv-sender">
              {{ m.fromAgentName }}
            </div>
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
        @keydown.enter.exact="onEnter"
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

// IME (한글/일본어) 조합 중 Enter 는 무시 — 조합 완료 후 다음 Enter 가 전송.
// 조합 중 Enter 를 잡으면 send 직후 composition end 결과가 textarea 에 다시 들어가 초기화가 안 보임.
function onEnter(e: KeyboardEvent): void {
  if (e.isComposing) return;
  e.preventDefault();
  void onSend();
}

function scrollToBottom(): void {
  if (!bodyRef.value) return;
  bodyRef.value.scrollTop = bodyRef.value.scrollHeight;
}

watch(() => props.messages.length, () => {
  void nextTick().then(scrollToBottom);
});

function statusLabel(s: AgentStatus): string {
  return { active: '작업중', waiting: '응답 대기', idle: '대기중', offline: '오프라인', compacting: '압축 중', error: '오류' }[s] ?? s;
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
.conv-view {
  display: flex; flex-direction: column;
  background: rgba(15, 23, 41, 0.4);
  flex: 1; min-width: 0; min-height: 0;
}

.conv-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 22px;
  background: rgba(20, 28, 48, 0.3);
  border-bottom: 1px solid #1E2738;
  flex-shrink: 0;
}
.conv-head.empty { justify-content: center; color: #6B7785; }
.cv-placeholder { font-size: 13px; }
.cv-back {
  display: none; padding: 6px 10px;
  background: transparent; border: none; cursor: pointer;
  font-size: 18px; color: #8B95A5;
}
.cv-avatar {
  width: 38px; height: 38px; border-radius: 50%;
  background: linear-gradient(135deg, #2A3447, #1A2030);
  border: 1px solid #2A3447;
  display: flex; align-items: center; justify-content: center; font-size: 18px;
}
.cv-title { display: flex; flex-direction: column; gap: 2px; }
.cv-name { font-size: 14px; font-weight: 700; color: #E5E9EE; }
.cv-meta { font-size: 11px; color: #8B95A5; }

.conv-body { flex: 1; overflow-y: auto; padding: 24px 28px; }
.cv-empty { color: #6B7785; font-size: 13px; text-align: center; margin-top: 40px; }

.cv-msgs { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 14px; }
.cv-msg { display: flex; animation: fadeIn .2s ease-out; }
.cv-msg.mine { justify-content: flex-end; }
.cv-msg.theirs { justify-content: flex-start; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cv-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 13px; line-height: 1.55;
  word-break: break-word; white-space: pre-wrap;
}
.cv-msg.mine .cv-bubble {
  background: linear-gradient(135deg, #4F7FFF, #7C5CFF);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 14px rgba(79, 127, 255, 0.25);
}
.cv-msg.theirs .cv-bubble {
  background: #1F2937; color: #E5E9EE;
  border: 1px solid #2A3447;
  border-bottom-left-radius: 4px;
}
.cv-sender {
  font-size: 11px; color: #8B95A5; font-weight: 600;
  margin-bottom: 3px;
}
.cv-content { font-size: 13px; line-height: 1.55; }
.cv-foot { display: flex; gap: 6px; align-items: center; margin-top: 4px; font-size: 10px; color: #6B7785; }
.cv-status.sent     { color: #6B7785; }
.cv-status.delivered{ color: #6BB6FF; }
.cv-status.replied  { color: #6BB6FF; font-weight: 700; }
.cv-status.failed   { color: #F87171; font-weight: 700; }

/* code block (markdown 또는 사용자 입력) */
.cv-bubble :deep(pre) {
  background: rgba(0, 0, 0, 0.3); border: 1px solid #2A3447;
  padding: 8px 10px; border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px;
  overflow-x: auto; margin: 6px 0;
}
.cv-msg.mine .cv-bubble :deep(pre) { background: rgba(0,0,0,0.2); border-color: rgba(255,255,255,0.15); }
.cv-bubble :deep(code) {
  background: rgba(0, 0, 0, 0.3); padding: 1px 5px; border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11.5px;
}
.cv-msg.mine .cv-bubble :deep(code) { background: rgba(0,0,0,0.2); }

.conv-input {
  border-top: 1px solid #1E2738;
  padding: 16px 22px;
  background: rgba(15, 23, 41, 0.6);
  backdrop-filter: blur(8px);
  flex-shrink: 0;
  display: flex; gap: 10px; align-items: flex-end;
}
.cv-textarea {
  flex: 1; resize: none; padding: 10px 14px;
  font-size: 13px; line-height: 1.55; font-family: inherit;
  background: #1A2030; border: 1px solid #2A3447; border-radius: 12px;
  color: #E5E9EE;
  transition: border-color .15s, box-shadow .15s;
}
.cv-textarea::placeholder { color: #4B5563; }
.cv-textarea:focus {
  outline: none; border-color: #4F7FFF;
  box-shadow: 0 0 0 3px rgba(79, 127, 255, 0.15);
}
.cv-textarea:disabled { background: #161B26; }
.cv-send {
  padding: 10px 20px; font-size: 13px; font-weight: 600;
  background: linear-gradient(135deg, #4F7FFF, #7C5CFF);
  color: #fff; border: none; border-radius: 10px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(79, 127, 255, 0.3);
  transition: transform .1s, box-shadow .15s;
}
.cv-send:hover:not(:disabled) {
  box-shadow: 0 6px 18px rgba(79, 127, 255, 0.5);
  transform: translateY(-1px);
}
.cv-send:active:not(:disabled) { transform: translateY(0); }
.cv-send:disabled {
  background: #2A3447; color: #6B7785;
  cursor: not-allowed; box-shadow: none;
}

/* scrollbar */
.conv-body::-webkit-scrollbar { width: 10px; }
.conv-body::-webkit-scrollbar-track { background: transparent; }
.conv-body::-webkit-scrollbar-thumb { background: #2A3447; border-radius: 5px; border: 2px solid transparent; background-clip: padding-box; }
.conv-body::-webkit-scrollbar-thumb:hover { background: #3A4A66; background-clip: padding-box; }

/* 모바일 */
@media (max-width: 768px) {
  .cv-back { display: block; }
}
</style>
