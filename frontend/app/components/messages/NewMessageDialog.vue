<template>
  <Teleport to="body">
    <div v-if="open" class="popup-overlay" @click.self="emit('close')">
      <div class="popup-box" role="dialog">
        <header class="popup-head">
          <h3>새 메시지{{ totalChecked > 1 ? ` (${totalChecked}명에게)` : '' }}</h3>
          <button class="popup-close" type="button" @click="emit('close')">×</button>
        </header>

        <div class="popup-body">
          <div class="form_field">
            <label class="form_label">받는 AI <span class="required">*</span></label>
            <div class="checkbox-list">
              <label
                v-for="a in agents"
                :key="a.agentId"
                class="checkbox-row"
                :class="{ disabled: !isReceivable(a) || (lockTo && a.agentId === initialToAgentId) }">
                <input
                  type="checkbox"
                  :value="a.agentId"
                  :checked="selectedSet.has(a.agentId)"
                  :disabled="!isReceivable(a) || (lockTo && a.agentId === initialToAgentId)"
                  @change="onToggle(a.agentId, ($event.target as HTMLInputElement).checked)" />
                <span class="checkbox-label">
                  {{ a.agentName }}{{ receivableSuffix(a) }}
                </span>
              </label>
            </div>
            <span class="form_help">
              완료 상태이거나 컨텍스트가 90% 초과한 AI 는 수신할 수 없습니다.
              <template v-if="lockTo && initialToAgentId">
                · 사전 선택된 수신자는 해제할 수 없습니다.
              </template>
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
                  :disabled="!isSendable(a) || selectedSet.has(a.agentId)">
                  {{ a.agentName }}{{ sendableSuffix(a) }}
                </option>
              </select>
            </div>
            <span class="form_help">발신자 역할을 할 AI 를 선택하세요. 받는 AI 와 같은 AI 는 선택할 수 없습니다.</span>
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
            {{ submitting ? '보내는 중…' : (totalChecked > 1 ? `${totalChecked}명에게 보내기` : '보내기') }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { AgentItem } from '~/vo/agents/AgentVo';
import type { MessageBroadcastRequest } from '~/vo/messages/MessageVo';

const props = withDefaults(defineProps<{
  open: boolean;
  agents: AgentItem[];
  initialFromAgentId?: string | null;
  initialToAgentId?: string | null;
  /** true 면 initialToAgentId 가 사전 체크 + 해제 불가 (대시보드 카드 메뉴에서 사용) */
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
  (e: 'submit', request: MessageBroadcastRequest): void;
}>();

const form = reactive({
  fromAgentId: '',
  content: ''
});
const selectedSet = reactive<Set<string>>(new Set<string>());

const totalChecked = computed(() => selectedSet.size);

watch(() => props.open, (next) => {
  if (next) {
    form.fromAgentId = props.initialFromAgentId ?? '';
    form.content = '';
    selectedSet.clear();
    if (props.initialToAgentId) selectedSet.add(props.initialToAgentId);
  }
});

function onToggle(agentId: string, checked: boolean): void {
  if (checked) selectedSet.add(agentId);
  else selectedSet.delete(agentId);
}

function isSendable(a: AgentItem): boolean {
  return a.status !== 'done';
}

function isReceivable(a: AgentItem): boolean {
  if (a.status === 'done') return false;
  if (a.contextPct !== null && a.contextPct >= 90) return false;
  return true;
}

function sendableSuffix(a: AgentItem): string {
  if (a.status === 'done') return ' (완료 — 발신 불가)';
  if (a.status === 'idle') return ' (쉬는 중)';
  return ' (작업중)';
}

function receivableSuffix(a: AgentItem): string {
  if (a.status === 'done') return ' (완료 — 수신 불가)';
  if (a.contextPct !== null && a.contextPct >= 90) return ` (컨텍스트 ${a.contextPct}% — 수신 불가)`;
  if (a.status === 'idle') return ' (쉬는 중)';
  return ' (작업중)';
}

const canSubmit = computed(() => {
  if (form.fromAgentId.length === 0) return false;
  if (selectedSet.size === 0) return false;
  if (selectedSet.has(form.fromAgentId)) return false;
  return form.content.trim().length > 0;
});

function onSubmit(): void {
  if (!canSubmit.value || props.submitting) return;
  emit('submit', {
    fromAgentId: form.fromAgentId,
    toAgentIds: Array.from(selectedSet),
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
  width: 540px; max-width: calc(100vw - 40px);
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
.popup-body { padding: 20px; max-height: 70vh; overflow-y: auto; }
.popup-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 20px; border-top: 1px solid #F0F2F5;
}

.form_field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.form_label { font-size: 13px; font-weight: 600; color: #333; }
.form_label .required { color: #E53935; }
.form_help { font-size: 12px; color: #AAB4BE; line-height: 1.5; }
.form_error {
  margin: 0; padding: 8px 12px; border-radius: 6px;
  background: #FFE5E9; color: #B22B45; font-size: 12px;
}

.checkbox-list {
  display: flex; flex-direction: column; gap: 4px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  padding: 8px 6px; background: #fff;
  max-height: 220px; overflow-y: auto;
}
.checkbox-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 4px;
  cursor: pointer; user-select: none;
}
.checkbox-row:hover:not(.disabled) { background: #F8FAFC; }
.checkbox-row.disabled {
  cursor: not-allowed; color: #94A3B8;
}
.checkbox-row input[type="checkbox"] {
  width: 16px; height: 16px; cursor: inherit;
}
.checkbox-label {
  font-size: 13px; color: inherit;
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
