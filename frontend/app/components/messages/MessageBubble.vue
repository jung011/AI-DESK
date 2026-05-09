<template>
  <div :id="`msg-${message.messageId}`" class="msg-row" :class="outgoing ? 'outgoing' : 'incoming'">
    <div class="msg-stack">
      <!-- 답장 인용 — replyToMessageId 가 있고 같은 대화에 원본이 보이면 표시 -->
      <button
        v-if="quotedMessage"
        type="button"
        class="msg-quote"
        :class="{ outgoing }"
        :title="`원본 메시지로 이동`"
        @click="scrollToOriginal">
        <span class="msg-quote-author">↩️ {{ quotedMessage.fromAgentName }}</span>
        <span class="msg-quote-content">{{ truncate(quotedMessage.content, 80) }}</span>
      </button>
      <span
        v-else-if="message.replyToMessageId"
        class="msg-quote-missing"
        :class="{ outgoing }"
        title="원본 메시지가 현재 대화에 보이지 않습니다 — 다른 대화의 답장이거나 한도(200건) 밖일 수 있습니다.">
        ↩️ <em>다른 대화의 답장</em>
      </span>

      <div class="msg-bubble">{{ message.content }}</div>
      <div class="msg-meta">
        <span>{{ formatTime(message.createdAt) }}</span>
        <span v-if="outgoing" class="msg-status" :class="message.status">
          {{ statusLabel }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { MessageItem } from '~/vo/messages/MessageVo';
import { useMessagesStore } from '~/stores/messages';

const props = defineProps<{
  message: MessageItem;
  /** true 면 오른쪽 파란 버블 (내가 보낸 것), false 면 왼쪽 흰 버블 (상대가 보낸 것) */
  outgoing: boolean;
}>();

const messagesStore = useMessagesStore();

/** 답장의 원본 메시지를 현재 타임라인에서 찾아온다. 없으면 null. */
const quotedMessage = computed<MessageItem | null>(() => {
  const id = props.message.replyToMessageId;
  if (!id) return null;
  return messagesStore.messages.find(m => m.messageId === id) ?? null;
});

const statusLabel = computed(() => {
  switch (props.message.status) {
    case 'sent':      return '발송됨';
    case 'delivered': return '전달됨';
    case 'replied':   return '✓ 답변 받음';
    case 'failed':    return props.message.errorReason ? `실패: ${props.message.errorReason}` : '실패';
    default:          return props.message.status;
  }
});

function formatTime(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function scrollToOriginal(): void {
  if (!quotedMessage.value) return;
  const el = document.getElementById(`msg-${quotedMessage.value.messageId}`);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('msg-row-flash');
    setTimeout(() => el.classList.remove('msg-row-flash'), 1600);
  }
}
</script>

<style scoped>
.msg-row { display: flex; gap: 10px; margin-bottom: 14px; align-items: flex-start; }
.msg-row.outgoing { flex-direction: row-reverse; }

.msg-stack {
  display: flex; flex-direction: column;
  align-items: flex-start;
  max-width: 70%;
}
.msg-row.outgoing .msg-stack { align-items: flex-end; }

.msg-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px; line-height: 1.55;
  word-break: break-word;
  white-space: pre-wrap;
}
.msg-row.incoming .msg-bubble {
  background: #fff; color: #333;
  border: 1px solid #E0E5EC; border-top-left-radius: 4px;
}
.msg-row.outgoing .msg-bubble {
  background: #0062ff; color: #fff;
  border-top-right-radius: 4px;
}

.msg-quote, .msg-quote-missing {
  display: inline-flex; flex-direction: column; gap: 2px;
  padding: 5px 10px; margin-bottom: 4px;
  border-left: 3px solid #94A3B8;
  background: #F8FAFC;
  border-radius: 4px;
  font-size: 11px; color: #475569;
  text-align: left; cursor: pointer; max-width: 100%;
  border-top: none; border-right: none; border-bottom: none;
  transition: background .12s;
}
.msg-quote:hover { background: #EEF2FF; }
.msg-quote.outgoing, .msg-quote-missing.outgoing {
  background: rgba(0, 98, 255, .07);
  border-left-color: #0062ff;
}
.msg-quote.outgoing:hover { background: rgba(0, 98, 255, .14); }
.msg-quote-missing { cursor: default; opacity: .8; }
.msg-quote-missing:hover { background: #F8FAFC; }
.msg-quote-author { font-weight: 600; color: #475569; }
.msg-quote-content {
  color: #94A3B8; line-height: 1.4;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 320px;
}

.msg-meta {
  font-size: 11px; color: #AAB4BE; margin-top: 4px;
  display: flex; align-items: center; gap: 6px;
}
.msg-row.outgoing .msg-meta { justify-content: flex-end; }

.msg-status { display: inline-flex; align-items: center; font-weight: 500; }
.msg-status.sent      { color: #AAB4BE; }
.msg-status.delivered { color: #0062ff; }
.msg-status.replied   { color: #2E7D32; }
.msg-status.failed    { color: #E53935; }
</style>

<style>
/* 전역 — 다른 컴포넌트에서 scrollToOriginal 시 잠시 강조 */
.msg-row-flash > .msg-stack > .msg-bubble {
  box-shadow: 0 0 0 3px rgba(255, 193, 7, .55);
  transition: box-shadow .3s;
}
</style>
