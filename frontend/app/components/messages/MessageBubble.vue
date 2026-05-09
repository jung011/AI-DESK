<template>
  <div class="msg-row" :class="outgoing ? 'outgoing' : 'incoming'">
    <div>
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

const props = defineProps<{
  message: MessageItem;
  /** true 면 오른쪽 파란 버블 (내가 보낸 것), false 면 왼쪽 흰 버블 (상대가 보낸 것) */
  outgoing: boolean;
}>();

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
</script>

<style scoped>
.msg-row { display: flex; gap: 10px; margin-bottom: 14px; align-items: flex-start; }
.msg-row.outgoing { flex-direction: row-reverse; }

.msg-bubble {
  max-width: 70%;
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
