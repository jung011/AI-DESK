<template>
  <Teleport to="body">
    <div v-if="open" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal">
        <h3>＋ 새 Task 추가</h3>
        <div class="modal-field">
          <label class="modal-label">Task 내용</label>
          <textarea
            v-model="content"
            class="modal-input modal-textarea"
            placeholder="예: /tmp/foo 디렉토리 만들고 ls 결과 보고"
            :disabled="submitting" />
        </div>
        <div class="modal-field">
          <label class="modal-label">담당 AI <span class="modal-label-hint">(온라인 만)</span></label>
          <select v-model="agentId" class="modal-input" :disabled="submitting">
            <option value="">(선택)</option>
            <option v-for="a in onlineAgents" :key="a.agentId" :value="a.agentId">{{ a.agentName }}</option>
          </select>
          <p v-if="onlineAgents.length === 0" class="modal-empty-hint">
            온라인 AI 가 없어요. 대시보드에서 *클로드 열기* 로 시작 후 다시 시도.
          </p>
        </div>
        <div class="modal-field">
          <label class="modal-label">첨부 파일 (선택)</label>
          <div class="modal-attach-row">
            <button class="btn-attach" :disabled="submitting || uploading" @click="onAttachClick">📎 파일 추가</button>
            <input ref="fileInput" type="file" multiple style="display:none" @change="onFileChange" />
            <span class="modal-attach-hint">{{ uploading ? '⏳ 업로드 중…' : 'PNG / PDF / TXT 등 · 최대 5MB' }}</span>
          </div>
          <ul v-if="pending.length > 0" class="modal-attach-list">
            <li v-for="a in pending" :key="a.attachmentId" class="modal-attach-chip">
              <span class="modal-attach-icon">{{ icon(a.contentType) }}</span>
              <span class="modal-attach-name">{{ a.originalFilename }}</span>
              <span class="modal-attach-size">{{ formatSize(a.sizeBytes) }}</span>
              <button class="modal-attach-x" @click="removeAttach(a.attachmentId)">✕</button>
            </li>
          </ul>
        </div>
        <div v-if="errorMsg" class="modal-error">{{ errorMsg }}</div>
        <div class="modal-actions">
          <button class="btn-cancel" :disabled="submitting" @click="$emit('close')">취소</button>
          <button class="btn-submit" :disabled="!canSubmit || submitting" @click="submit">
            {{ submitting ? '추가 중…' : '▶ 추가' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { AgentItem } from '~/vo/agents/AgentVo';

interface AttachmentItem {
  attachmentId: string;
  originalFilename: string;
  contentType: string;
  sizeBytes: number;
}

const props = defineProps<{ open: boolean; agents: AgentItem[] }>();
const emit = defineEmits<{ (e: 'close'): void; (e: 'created'): void }>();

const { $api } = useNuxtApp();
const { createTask } = useTasks();

const content = ref('');
const agentId = ref('');
const pending = ref<AttachmentItem[]>([]);
const submitting = ref(false);
const uploading = ref(false);
const errorMsg = ref<string | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);

// 온라인 AI 만 — TODO status 도 *수신 가능* path 하지만 *처리 시작* 위해서는 active.
// active / waiting / idle 모두 *online* 으로 통합 ([[useAgents]] 의 ONLINE_BACKEND_STATUSES).
const ONLINE_STATUSES = new Set(['active', 'waiting', 'idle']);
const onlineAgents = computed(() => props.agents.filter((a) => ONLINE_STATUSES.has(a.status)));
const canSubmit = computed(() => content.value.trim().length > 0 && !!agentId.value);

watch(() => props.open, (v) => {
  if (v) {
    content.value = '';
    agentId.value = '';
    pending.value = [];
    errorMsg.value = null;
  }
});

function icon(ct: string): string {
  if (ct.startsWith('image/')) return '🖼';
  if (ct.includes('pdf')) return '📄';
  return '📎';
}
function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function onAttachClick(): void { fileInput.value?.click(); }

async function onFileChange(e: Event): Promise<void> {
  const target = e.target as HTMLInputElement;
  const files = Array.from(target.files ?? []);
  target.value = '';
  if (!agentId.value) {
    errorMsg.value = '담당 AI 를 먼저 선택해줘';
    return;
  }
  uploading.value = true;
  try {
    for (const f of files) {
      const fd = new FormData();
      fd.append('file', f);
      fd.append('ownerAgentId', agentId.value);
      const res = await $api<{ result: number; message: string; data: AttachmentItem }>(
        '/api/attachments', { method: 'POST', body: fd }
      );
      if (res.result === 0) pending.value.push(res.data);
      else { errorMsg.value = res.message; break; }
    }
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    uploading.value = false;
  }
}

function removeAttach(id: string): void {
  pending.value = pending.value.filter((a) => a.attachmentId !== id);
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return;
  submitting.value = true;
  errorMsg.value = null;
  try {
    const t = await createTask({
      agentId: agentId.value,
      content: content.value.trim(),
      attachmentIds: pending.value.map((a) => a.attachmentId),
    });
    if (t) emit('created');
    else errorMsg.value = 'task 박기 실패';
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: #1E2738; border: 1px solid #2A3950; border-radius: 12px; padding: 20px; width: 480px; max-width: 90vw; }
.modal h3 { margin: 0 0 14px; color: #FBBF24; font-size: 15px; }
.modal-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.modal-label { font-size: 11px; color: #8B95A5; font-weight: 600; }
.modal-label-hint { color: #6B7280; font-weight: 400; margin-left: 6px; }
.modal-empty-hint { color: #FBBF24; font-size: 11px; margin: 4px 0 0; padding: 0; }
.modal-input { background: #0F1729; border: 1px solid #2A3950; color: #E5EBF5; border-radius: 6px; padding: 8px 10px; font-size: 13px; font-family: inherit; }
.modal-textarea { min-height: 80px; resize: vertical; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.modal-error { color: #FCA5A5; font-size: 12px; padding: 8px 10px; background: rgba(239, 68, 68, 0.1); border-radius: 6px; margin-bottom: 10px; }
.btn-cancel { background: transparent; color: #8B95A5; border: 1px solid #2A3950; border-radius: 6px; padding: 7px 14px; font-size: 12px; cursor: pointer; }
.btn-submit { background: #2A4A8E; color: white; border: none; border-radius: 6px; padding: 7px 14px; font-size: 12px; cursor: pointer; }
.btn-submit:disabled { background: #2A3950; color: #6B7280; cursor: not-allowed; }
.modal-attach-row { display: flex; align-items: center; gap: 10px; }
.btn-attach { background: #2A3950; color: #93C5FD; border: 1px dashed #4B5563; border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer; }
.btn-attach:hover:not(:disabled) { background: #354560; border-color: #93C5FD; }
.modal-attach-hint { color: #6B7280; font-size: 11px; }
.modal-attach-list { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-direction: column; gap: 6px; }
.modal-attach-chip { display: flex; align-items: center; gap: 8px; background: rgba(42, 74, 142, 0.18); border: 1px solid rgba(42, 74, 142, 0.4); border-radius: 6px; padding: 6px 10px; }
.modal-attach-icon { font-size: 14px; }
.modal-attach-name { color: #E5EBF5; font-size: 12px; flex: 1; }
.modal-attach-size { color: #8B95A5; font-size: 10px; }
.modal-attach-x { background: transparent; color: #6B7280; border: none; cursor: pointer; font-size: 12px; padding: 0 4px; }
.modal-attach-x:hover { color: #F87171; }
</style>
