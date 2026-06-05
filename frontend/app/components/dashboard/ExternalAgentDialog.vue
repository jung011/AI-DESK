<template>
  <div v-if="modelValue" class="ext-modal-backdrop" @click.self="onClose">
    <div class="ext-modal">
      <header class="ext-modal-head">
        <h3>외부 AI 등록</h3>
        <button class="ext-modal-close" @click="onClose">×</button>
      </header>

      <div v-if="step === 'form'" class="ext-modal-body">
        <p class="ext-modal-help">
          외부 service (챗봇, 자동화 등) 를 사내 동료처럼 합류시킵니다.
          이름은 채팅에 그대로 노출됩니다.
        </p>
        <label class="ext-modal-label">
          <span>이름</span>
          <input
            v-model="name"
            class="ext-modal-input"
            placeholder="예: 챗봇 봇, 자동 빌드러"
            @keydown.enter="submit"
            ref="nameInput"
          >
        </label>
        <div v-if="errorMsg" class="ext-modal-error">{{ errorMsg }}</div>
        <footer class="ext-modal-foot">
          <button class="ext-btn" @click="onClose">취소</button>
          <button class="ext-btn primary" :disabled="!name.trim() || busy" @click="submit">
            {{ busy ? '생성 중…' : '생성' }}
          </button>
        </footer>
      </div>

      <div v-else-if="step === 'token'" class="ext-modal-body">
        <p class="ext-modal-help token-warn">
          ⚠️ Token 은 <strong>지금 한 번만</strong> 표시됩니다. 외부 service 의
          환경변수 (예: <code>AIDESK_BEARER_TOKEN</code>) 에 즉시 저장하세요.
          이후 복원 불가 — 분실 시 <strong>token rotate</strong> 로 재발급.
        </p>
        <label class="ext-modal-label">
          <span>Agent ID</span>
          <input class="ext-modal-input mono" :value="created?.agentId" readonly>
        </label>
        <label class="ext-modal-label">
          <span>Token</span>
          <input class="ext-modal-input mono" :value="created?.token" readonly>
        </label>
        <div class="ext-modal-actions">
          <button class="ext-btn" @click="copyToken">{{ copied ? '복사됨!' : '토큰 복사' }}</button>
        </div>
        <footer class="ext-modal-foot">
          <button class="ext-btn primary" @click="onClose">완료</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface ExternalAgentTokenRs {
  agentId: string;
  agentName: string;
  token: string;
}

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void;
  (e: 'created'): void;
}>();

const step = ref<'form' | 'token'>('form');
const name = ref('');
const busy = ref(false);
const errorMsg = ref<string | null>(null);
const created = ref<ExternalAgentTokenRs | null>(null);
const copied = ref(false);
const nameInput = ref<HTMLInputElement | null>(null);

watch(() => props.modelValue, (open) => {
  if (open) {
    step.value = 'form';
    name.value = '';
    busy.value = false;
    errorMsg.value = null;
    created.value = null;
    copied.value = false;
    nextTick(() => nameInput.value?.focus());
  }
});

async function submit() {
  const trimmed = name.value.trim();
  if (!trimmed) return;
  busy.value = true;
  errorMsg.value = null;
  try {
    const env = await $api<ApiEnvelope<ExternalAgentTokenRs>>('/api/agents/external', {
      method: 'POST',
      body: { agentName: trimmed },
    });
    created.value = env.data;
    step.value = 'token';
    emit('created');
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function copyToken() {
  if (!created.value?.token) return;
  try {
    await navigator.clipboard.writeText(created.value.token);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    /* clipboard 거부 — fallback 으로 input select */
  }
}

function onClose() {
  emit('update:modelValue', false);
}
</script>

<style scoped>
.ext-modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.ext-modal {
  background: #fff; border-radius: 8px;
  width: 480px; max-width: 92vw;
  box-shadow: 0 10px 40px rgba(0,0,0,.2);
}
.ext-modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #E5E9EE;
}
.ext-modal-head h3 { margin: 0; font-size: 16px; }
.ext-modal-close {
  background: none; border: none; font-size: 24px; cursor: pointer; color: #999;
  line-height: 1; padding: 0;
}
.ext-modal-body { padding: 20px; }
.ext-modal-help { font-size: 13px; color: #555; margin: 0 0 16px; line-height: 1.5; }
.ext-modal-help.token-warn {
  background: #FFF7E1; border-left: 3px solid #F0AD4E;
  padding: 10px 12px; border-radius: 3px;
}
.ext-modal-help code {
  background: #F4F6FB; padding: 1px 4px; border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px;
}
.ext-modal-label {
  display: block; margin-bottom: 12px;
}
.ext-modal-label span {
  display: block; font-size: 12px; font-weight: 600; color: #444; margin-bottom: 4px;
}
.ext-modal-input {
  width: 100%; padding: 8px 10px; border: 1px solid #D4DCE4; border-radius: 4px;
  font-size: 14px; box-sizing: border-box;
}
.ext-modal-input.mono {
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px;
  background: #F8FAFC;
}
.ext-modal-error {
  color: #C0392B; font-size: 12px; margin-bottom: 12px;
}
.ext-modal-actions { margin-bottom: 12px; }
.ext-modal-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding-top: 8px; border-top: 1px solid #E5E9EE;
}
.ext-btn {
  padding: 6px 14px; border: 1px solid #D4DCE4; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 13px;
}
.ext-btn.primary {
  background: #2D7FF9; color: #fff; border-color: #2D7FF9;
}
.ext-btn.primary:disabled {
  background: #B0C8E3; border-color: #B0C8E3; cursor: not-allowed;
}
</style>
