<template>
  <Teleport to="body">
    <div v-if="open" class="popup-overlay" @click.self="emit('close')">
      <div class="popup-box" role="dialog">
        <header class="popup-head">
          <h3>새 메시지</h3>
          <button class="popup-close" type="button" @click="emit('close')">×</button>
        </header>

        <div class="popup-body">
          <div class="form_field">
            <label class="form_label">받는 AI <span class="required">*</span></label>
            <div class="select-wrap">
              <select v-model="form.toAgentId" :disabled="lockTo">
                <option value="">선택하세요…</option>
                <option
                  v-for="a in agents"
                  :key="a.agentId"
                  :value="a.agentId"
                  :disabled="!isReceivable(a) || a.agentId === form.fromAgentId">
                  {{ a.agentName }}{{ receivableLabel(a) }}
                </option>
              </select>
            </div>
            <span class="form_help">
              완료 상태이거나 컨텍스트가 90% 초과한 AI 는 수신할 수 없습니다.
            </span>
          </div>

          <div class="form_field">
            <label class="form_label">보내는 AI <span class="required">*</span></label>
            <div class="select-wrap">
              <select v-model="form.fromAgentId">
                <option value="">선택하세요…</option>
                <option
                  v-for="a in agents"
                  :key="a.agentId"
                  :value="a.agentId"
                  :disabled="!isSendable(a) || a.agentId === form.toAgentId">
                  {{ a.agentName }}{{ sendableLabel(a) }}
                </option>
              </select>
            </div>
            <span class="form_help">발신자 역할을 할 AI 를 선택하세요.</span>
          </div>

          <div class="form_field">
            <label class="form_label">메시지 본문 <span class="required">*</span></label>
            <textarea
              v-model="form.content"
              :maxlength="1000"
              placeholder="질문이나 요청을 입력하세요"
              rows="5" />
            <span class="form_help">{{ form.content.length }} / 1000</span>
          </div>

          <p v-if="errorMessage" class="form_error">{{ errorMessage }}</p>
        </div>

        <footer class="popup-foot">
          <button class="btn normal type_v2" type="button" :disabled="submitting" @click="emit('close')">취소</button>
          <button
            class="btn normal type_v1"
            type="button"
            :disabled="!canSubmit || submitting"
            @click="onSubmit">
            {{ submitting ? '보내는 중…' : '보내기' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { AgentItem } from '~/vo/agents/AgentVo';
import type { MessageCreateRequest } from '~/vo/messages/MessageVo';

const props = withDefaults(defineProps<{
  open: boolean;
  agents: AgentItem[];
  initialFromAgentId?: string | null;
  initialToAgentId?: string | null;
  lockTo?: boolean;
  submitting?: boolean;
  errorMessage?: string | null;
}>(), {
  initialFromAgentId: null,
  initialToAgentId: null,
  lockTo: false,
  submitting: false,
  errorMessage: null
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'submit', request: MessageCreateRequest): void;
}>();

const form = reactive({
  fromAgentId: '',
  toAgentId: '',
  content: ''
});

watch(() => props.open, (next) => {
  if (next) {
    form.fromAgentId = props.initialFromAgentId ?? '';
    form.toAgentId = props.initialToAgentId ?? '';
    form.content = '';
  }
});

function isSendable(a: AgentItem): boolean {
  return a.status !== 'done';
}

function isReceivable(a: AgentItem): boolean {
  if (a.status === 'done') return false;
  if (a.contextPct !== null && a.contextPct >= 90) return false;
  return true;
}

function sendableLabel(a: AgentItem): string {
  if (a.status === 'done') return ' (완료 — 발신 불가)';
  if (a.status === 'idle') return ' (쉬는 중)';
  return ' (작업중)';
}

function receivableLabel(a: AgentItem): string {
  if (a.status === 'done') return ' (완료 — 수신 불가)';
  if (a.contextPct !== null && a.contextPct >= 90) return ` (컨텍스트 ${a.contextPct}% — 수신 불가)`;
  if (a.status === 'idle') return ' (쉬는 중)';
  return ' (작업중)';
}

const canSubmit = computed(() =>
  form.fromAgentId.length > 0 &&
  form.toAgentId.length > 0 &&
  form.fromAgentId !== form.toAgentId &&
  form.content.trim().length > 0
);

function onSubmit(): void {
  if (!canSubmit.value || props.submitting) return;
  emit('submit', {
    fromAgentId: form.fromAgentId,
    toAgentId: form.toAgentId,
    content: form.content.trim()
  });
}
</script>

<style scoped>
.popup-overlay {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.popup-box {
  width: 520px; max-width: calc(100vw - 40px);
  background: #fff; border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
  display: flex; flex-direction: column;
}
.popup-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #F0F2F5;
}
.popup-head h3 { font-size: 15px; font-weight: 700; color: #101010; margin: 0; }
.popup-close {
  width: 28px; height: 28px;
  background: none; border: none; font-size: 22px;
  color: #94A3B8; cursor: pointer; line-height: 1;
}
.popup-close:hover { color: #475569; }
.popup-body { padding: 20px; }
.popup-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 20px; border-top: 1px solid #F0F2F5;
}

.form_field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.form_label { font-size: 13px; font-weight: 600; color: #333; }
.form_label .required { color: #E53935; }
.form_help { font-size: 12px; color: #AAB4BE; }
.form_error {
  margin: 0; padding: 8px 12px; border-radius: 6px;
  background: #FFE5E9; color: #B22B45; font-size: 12px;
}

.select-wrap { position: relative; }
.select-wrap select {
  width: 100%; height: 36px; padding: 0 32px 0 12px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; color: #333; background: #fff;
  appearance: none; cursor: pointer;
}
.select-wrap select:disabled { background: #F8FAFC; cursor: not-allowed; }
.select-wrap::after {
  content: ''; position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
  width: 0; height: 0;
  border-left: 4px solid transparent; border-right: 4px solid transparent;
  border-top: 5px solid #999; pointer-events: none;
}

.form_field textarea {
  padding: 10px 12px; border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; font-family: inherit; resize: vertical;
}
.form_field textarea:focus { outline: none; border-color: #0062ff; }

.btn.normal {
  display: inline-flex; align-items: center; height: 36px;
  padding: 0 16px; border-radius: 6px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent;
}
.btn.normal.type_v1 { background: #0062ff; color: #fff; }
.btn.normal.type_v1:hover:not(:disabled) { background: #0052d4; }
.btn.normal.type_v1:disabled { background: #94A3B8; cursor: not-allowed; }
.btn.normal.type_v2 {
  background: #fff; color: #475569; border-color: #D4DCE4;
}
.btn.normal.type_v2:hover:not(:disabled) { background: #F8FAFC; }
</style>
