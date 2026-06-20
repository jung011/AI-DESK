<template>
  <div v-if="modelValue" class="ext-modal-backdrop" @click.self="onClose">
    <div class="ext-modal">
      <header class="ext-modal-head">
        <h3>외부 AI Token Rotate</h3>
        <button class="ext-modal-close" @click="onClose">×</button>
      </header>

      <div v-if="step === 'confirm'" class="ext-modal-body">
        <p class="ext-modal-help">
          <strong>{{ agentName }}</strong> 의 token 을 새로 발급합니다.
          <br>옛 token 은 즉시 무효 — 운영 중인 mcp 가 있다면 새 token 으로 재설정 필요.
        </p>
        <div v-if="errorMsg" class="ext-modal-error">{{ errorMsg }}</div>
        <footer class="ext-modal-foot">
          <button class="ext-btn" @click="onClose">취소</button>
          <button class="ext-btn primary" :disabled="busy" @click="submit">
            {{ busy ? 'Rotate 중…' : 'Token 새로 발급' }}
          </button>
        </footer>
      </div>

      <div v-else-if="step === 'token'" class="ext-modal-body">
        <p class="ext-modal-help token-warn">
          ⚠️ Token 은 <strong>지금 한 번만</strong> 표시됩니다. 즉시 외부 service 의
          환경변수에 저장하세요. 옛 token 은 이미 무효 — 분실 시 또 rotate 필요.
        </p>
        <label class="ext-modal-label">
          <span>Agent ID</span>
          <input class="ext-modal-input mono" :value="agentId" readonly>
          <div class="ext-modal-actions">
            <button class="ext-btn" @click="copyAgentId">{{ idCopied ? '복사됨!' : 'Agent ID 복사' }}</button>
          </div>
        </label>
        <label class="ext-modal-label">
          <span>새 Token</span>
          <input class="ext-modal-input mono" :value="newToken" readonly>
          <div class="ext-modal-actions">
            <button class="ext-btn" @click="copyToken">{{ copied ? '복사됨!' : '토큰 복사' }}</button>
          </div>
        </label>

        <div class="ext-modal-label">
          <span>외부 운영 재설정 명령</span>
          <p class="ext-modal-help">
            기존 외부 AI 워크스페이스 디렉토리에서 한 번에 paste + Enter.
            <br>(binary 가 이미 있어도 재다운로드 — 옛 .pkg 가 있을 수도 있어 안전 차원.)
          </p>
          <pre class="ext-setup-script">{{ setupScript }}</pre>
          <div class="ext-modal-actions">
            <button class="ext-btn" @click="copySetupScript">{{ scriptCopied ? '복사됨!' : '명령 복사' }}</button>
          </div>
        </div>

        <footer class="ext-modal-foot">
          <button class="ext-btn primary" @click="onClose">완료</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface ExternalAgentTokenRs {
  agentId: string;
  agentName: string;
  token: string;
}

const props = defineProps<{
  modelValue: boolean;
  agentId: string;
  agentName: string;
}>();
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void;
  (e: 'rotated'): void;
}>();

const step = ref<'confirm' | 'token'>('confirm');
const busy = ref(false);
const errorMsg = ref<string | null>(null);
const newToken = ref<string>('');
const copied = ref(false);
const idCopied = ref(false);
const scriptCopied = ref(false);

// 재설정 script — ExternalAgentDialog 의 setupScript 와 동일 패턴. 옛 mcp 항목 remove 후 새 token 박음.
const setupScript = computed(() => {
  if (!newToken.value) return '';
  const backendUrl = window.location.origin;
  return `cat > /tmp/aidesk-setup.sh <<'AIDESK_EOF'
set -e
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/')
PLATFORM="\${OS}-\${ARCH}"

curl -fsSL -o aidesk-channel-mcp "${backendUrl}/api/external/mcp/aidesk-channel-mcp-\${PLATFORM}"
chmod +x aidesk-channel-mcp
[[ "\$OS" == "darwin" ]] && codesign --force --sign - aidesk-channel-mcp

claude mcp remove aidesk-channel-ext --scope local 2>/dev/null || true
claude mcp add aidesk-channel-ext --scope local --transport stdio \\
  --env "AIDESK_BEARER_TOKEN=${newToken.value}" \\
  --env "AIDESK_AGENT_ID=${props.agentId}" \\
  --env "AIDESK_API_URL=${backendUrl}" \\
  -- "$(pwd)/aidesk-channel-mcp"

echo "✓ Rotate setup 완료. claude code 재실행:"
echo "  claude --dangerously-load-development-channels server:aidesk-channel-ext"
AIDESK_EOF
bash /tmp/aidesk-setup.sh`;
});

watch(() => props.modelValue, (open) => {
  if (open) {
    step.value = 'confirm';
    busy.value = false;
    errorMsg.value = null;
    newToken.value = '';
    copied.value = false;
    idCopied.value = false;
    scriptCopied.value = false;
  }
});

async function submit() {
  busy.value = true;
  errorMsg.value = null;
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<ExternalAgentTokenRs>>(
      `/api/agents/external/${encodeURIComponent(props.agentId)}/token`,
      { method: 'POST' },
    );
    newToken.value = env.data.token;
    step.value = 'token';
    emit('rotated');
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fallthrough */ }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.top = '0';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    document.body.removeChild(ta);
  }
}

async function copyToken() {
  if (!newToken.value) return;
  if (await copyText(newToken.value)) {
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  }
}

async function copyAgentId() {
  if (await copyText(props.agentId)) {
    idCopied.value = true;
    setTimeout(() => { idCopied.value = false; }, 2000);
  }
}

async function copySetupScript() {
  if (!setupScript.value) return;
  if (await copyText(setupScript.value)) {
    scriptCopied.value = true;
    setTimeout(() => { scriptCopied.value = false; }, 2000);
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
  max-height: 90vh;
  display: flex; flex-direction: column;
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
.ext-modal-body { padding: 20px; overflow-y: auto; flex: 1 1 auto; min-height: 0; }
.ext-modal-help { font-size: 13px; color: #555; margin: 0 0 16px; line-height: 1.5; }
.ext-modal-help.token-warn {
  background: #FFF7E1; border-left: 3px solid #F0AD4E;
  padding: 10px 12px; border-radius: 3px;
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
.ext-setup-script {
  background: #1e1e1e; color: #e6e6e6; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; line-height: 1.5; padding: 12px; border-radius: 6px;
  max-height: 280px; overflow: auto; white-space: pre; margin: 6px 0 8px;
}
</style>
