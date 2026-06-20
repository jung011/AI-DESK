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
          <div class="ext-modal-actions">
            <button class="ext-btn" @click="copyAgentId">{{ idCopied ? '복사됨!' : 'Agent ID 복사' }}</button>
          </div>
        </label>
        <label class="ext-modal-label">
          <span>Token</span>
          <input class="ext-modal-input mono" :value="created?.token" readonly>
          <div class="ext-modal-actions">
            <button class="ext-btn" @click="copyToken">{{ copied ? '복사됨!' : '토큰 복사' }}</button>
          </div>
        </label>

        <!-- 외부 운영 setup 가이드 — 외부 AI 의 mac/linux 서버에서 그대로 실행 가능. -->
        <div class="ext-modal-label">
          <span>외부 운영 setup 명령</span>
          <p class="ext-modal-help">
            외부 AI 운영자에게 <strong>아래 명령 전체</strong>를 전달 → 외부 AI 의 워크스페이스 디렉토리에서 <strong>한 번에 paste + Enter</strong>.
            <br>(heredoc 패턴 — zsh / bash 모두 호환. binary 다운로드 + (mac) codesign + mcp 등록 자동.)
          </p>
          <pre class="ext-setup-script">{{ setupScript }}</pre>
          <div class="ext-modal-actions">
            <button class="ext-btn" @click="copySetupScript">{{ scriptCopied ? '복사됨!' : '명령 복사' }}</button>
          </div>
        </div>
        <p class="ext-modal-help">
          <strong>실행 후</strong> — 같은 디렉토리에서 claude code 시작:
          <br><code>claude --dangerously-load-development-channels server:aidesk-channel-ext</code>
          <br>= 사전 조건: claude code 설치. 사내 망에서 backend 접근 가능.
        </p>

        <footer class="ext-modal-foot">
          <button class="ext-btn primary" @click="onClose">완료</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
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
const idCopied = ref(false);
const scriptCopied = ref(false);
const nameInput = ref<HTMLInputElement | null>(null);

// 외부 운영 setup script — heredoc 안에 박아서 zsh paste 시 wrap / `!` history expansion 우회.
// 사용자가 그대로 paste 하면 /tmp/aidesk-setup.sh 에 저장 + bash 실행. 한 번에 완료.
const setupScript = computed(() => {
  if (!created.value) return '';
  const backendUrl = window.location.origin;
  const token = created.value.token;
  const agentId = created.value.agentId;
  return `cat > /tmp/aidesk-setup.sh <<'AIDESK_EOF'
set -e
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/')
PLATFORM="\${OS}-\${ARCH}"

# 1. binary download
curl -fsSL -o aidesk-channel-mcp "${backendUrl}/api/external/mcp/aidesk-channel-mcp-\${PLATFORM}"
chmod +x aidesk-channel-mcp

# 2. macOS Gatekeeper 우회 (linux skip)
[[ "\$OS" == "darwin" ]] && codesign --force --sign - aidesk-channel-mcp

# 3. claude code mcp 등록 (scope local — 현재 디렉토리만)
claude mcp remove aidesk-channel-ext --scope local 2>/dev/null || true
claude mcp add aidesk-channel-ext --scope local --transport stdio \\
  --env "AIDESK_BEARER_TOKEN=${token}" \\
  --env "AIDESK_AGENT_ID=${agentId}" \\
  --env "AIDESK_API_URL=${backendUrl}" \\
  -- "$(pwd)/aidesk-channel-mcp"

echo "✓ Setup 완료. 다음 명령으로 claude code 실행:"
echo "  claude --dangerously-load-development-channels server:aidesk-channel-ext"
AIDESK_EOF
bash /tmp/aidesk-setup.sh`;
});

watch(() => props.modelValue, (open) => {
  if (open) {
    step.value = 'form';
    name.value = '';
    busy.value = false;
    errorMsg.value = null;
    created.value = null;
    copied.value = false;
    idCopied.value = false;
    nextTick(() => nameInput.value?.focus());
  }
});

async function submit() {
  const trimmed = name.value.trim();
  if (!trimmed) return;
  busy.value = true;
  errorMsg.value = null;
  try {
    const { $api } = useNuxtApp();
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

// navigator.clipboard 는 secure context (https/localhost) 에서만 동작.
// 사설 도메인 + HTTP 환경 (aidesk.kaflix.internal) 에선 fail → execCommand fallback.
async function copyText(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fallthrough */
  }
  // Fallback — deprecated 지만 HTTP context 에서도 동작.
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
  if (!created.value?.token) return;
  if (await copyText(created.value.token)) {
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  }
}

async function copyAgentId() {
  if (!created.value?.agentId) return;
  if (await copyText(created.value.agentId)) {
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
.ext-setup-script {
  background: #1e1e1e; color: #e6e6e6; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; line-height: 1.5; padding: 12px; border-radius: 6px;
  max-height: 280px; overflow: auto; white-space: pre; margin: 6px 0 8px;
}
</style>
