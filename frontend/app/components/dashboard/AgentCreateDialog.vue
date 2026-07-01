<template>
  <Teleport to="body">
    <div v-if="open" class="popup-overlay" @click.self="emit('close')">
      <div class="popup-box" role="dialog" aria-labelledby="agent-create-title">
        <header class="popup-head">
          <h3 id="agent-create-title">AI 생성</h3>
          <button class="popup-close" type="button" @click="emit('close')">×</button>
        </header>

        <div class="popup-body">
          <div class="form_field">
            <label class="form_label">AI 이름 <span class="required">*</span></label>
            <input
              v-model="form.agentName"
              type="text"
              maxlength="50"
              placeholder="예: 코드 리뷰 AI" />
            <span class="form_help">생성할 AI 에이전트의 이름을 입력하세요. (최대 50자)</span>
          </div>

          <div class="form_field">
            <label class="form_label">워크스페이스 경로 <span class="required">*</span></label>
            <div class="workspace-input-row">
              <input
                v-model="form.workspaceDir"
                type="text"
                placeholder="예: /Users/username/workspace/my-project" />
              <button
                type="button"
                class="btn-browse"
                :disabled="browsing"
                @click="onBrowse">
                {{ browsing ? '선택 중…' : '찾아보기' }}
              </button>
            </div>
            <span class="form_help">AI가 작업할 로컬 폴더의 절대 경로를 입력하거나 “찾아보기”로 선택하세요. (예: /Users/me/proj 또는 C:/Users/me/proj)</span>
          </div>

          <div class="form_field">
            <label class="form_label">AI 모델 <span class="required">*</span></label>
            <div class="model-select-wrap">
              <select v-model="form.model">
                <option value="claude">claude</option>
                <option value="codex">codex</option>
                <option value="hermes">hermes</option>
              </select>
            </div>
            <span class="form_help">실행할 AI 모델을 선택하세요.</span>
          </div>

          <p v-if="errorMessage" class="form_error">{{ errorMessage }}</p>
        </div>

        <footer class="popup-foot">
          <button class="btn normal type_v2" type="button" :disabled="submitting" @click="emit('close')">취소</button>
          <button class="btn normal type_v1" type="button" :disabled="!canSubmit || submitting" @click="onSubmit">
            {{ submitting ? '생성 중…' : '생성' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { AgentCreateRequest } from '~/vo/agents/AgentVo';

const props = defineProps<{
  open: boolean;
  submitting?: boolean;
  errorMessage?: string | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'submit', request: AgentCreateRequest): void;
}>();

const form = reactive<AgentCreateRequest>({
  agentName: '',
  workspaceDir: '',
  model: 'claude'
});

const browsing = ref(false);

// 절대 경로 검증 — Unix(`/...`)와 Windows(`C:/...`, `C:\...`) 를 모두 허용 (OS 분기 없이 양쪽 호환).
const ABS_PATH_RE = /^([a-zA-Z]:[\\/]|\/).+/;
const canSubmit = computed(() =>
  form.agentName.trim().length > 0 &&
  ABS_PATH_RE.test(form.workspaceDir.trim()) &&
  ['claude', 'codex', 'hermes'].includes(form.model)
);

// 다이얼로그가 열릴 때마다 폼 초기화
watch(() => props.open, (next) => {
  if (next) {
    form.agentName = '';
    form.workspaceDir = '';
    form.model = 'claude';
    browsing.value = false;
  }
});

async function onBrowse(): Promise<void> {
  if (browsing.value) return;
  browsing.value = true;
  try {
    const { $helper } = useNuxtApp();
    const env = await $helper<{ rc: number; message?: string; path?: string }>(
      '/api/browse-workspace',
      { method: 'POST' }
    );
    if (env.rc !== 0) {
      // eslint-disable-next-line no-alert
      alert(env.message || '폴더 선택을 사용할 수 없습니다.');
      return;
    }
    // 빈 문자열 = 사용자 취소. 그대로 두고 무시한다.
    if (env.path) form.workspaceDir = env.path;
  } catch (e) {
    // eslint-disable-next-line no-alert
    alert(`폴더 선택 호출 실패 (헬퍼 가동 확인): ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    browsing.value = false;
  }
}

function onSubmit(): void {
  if (!canSubmit.value || props.submitting) return;
  emit('submit', {
    agentName: form.agentName.trim(),
    workspaceDir: form.workspaceDir.trim().replace(/\/$/, ''),
    model: form.model
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
  width: 480px; max-width: calc(100vw - 40px);
  background: var(--bg-card); border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
  display: flex; flex-direction: column;
}
.popup-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border);
}
.popup-head h3 { font-size: 15px; font-weight: 700; color: var(--text); margin: 0; }
.popup-close {
  width: 28px; height: 28px;
  background: none; border: none; font-size: 22px;
  color: var(--text-dim); cursor: pointer; line-height: 1;
}
.popup-close:hover { color: var(--text); }
.popup-body { padding: 20px; }
.popup-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 20px; border-top: 1px solid var(--border);
}

.form_field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.form_label { font-size: 13px; font-weight: 600; color: var(--text); }
.form_label .required { color: #F87171; }
.form_help { font-size: 12px; color: var(--text-dim); }
.form_error {
  margin: 0; padding: 8px 12px; border-radius: 6px;
  background: rgba(248, 113, 113, .12); color: #F87171; font-size: 12px;
}
.form_field input[type="text"] {
  height: 36px; padding: 0 12px;
  border: 1px solid var(--border); border-radius: 6px;
  font-size: 13px; color: var(--text); background: var(--bg);
}
.form_field input[type="text"]:focus { outline: none; border-color: #6BB6FF; }

.workspace-input-row { display: flex; gap: 8px; align-items: center; }
.workspace-input-row input { flex: 1; }
.btn-browse {
  flex-shrink: 0;
  height: 36px; padding: 0 14px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg-card); color: var(--text);
  font-size: 12px; font-weight: 600; cursor: pointer;
}
.btn-browse:hover:not(:disabled) { background: rgba(107, 182, 255, .1); border-color: #6BB6FF; color: #6BB6FF; }
.btn-browse:disabled { color: var(--text-dim); cursor: not-allowed; }

.model-select-wrap { position: relative; }
.model-select-wrap select {
  width: 100%; height: 36px; padding: 0 32px 0 12px;
  border: 1px solid var(--border); border-radius: 6px;
  font-size: 13px; color: var(--text); background: var(--bg);
  appearance: none; cursor: pointer;
}
.model-select-wrap select option { background: var(--bg-card); color: var(--text); }
.model-select-wrap::after {
  content: ''; position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
  width: 0; height: 0;
  border-left: 4px solid transparent; border-right: 4px solid transparent;
  border-top: 5px solid var(--text-muted); pointer-events: none;
}

.btn.normal {
  display: inline-flex; align-items: center; height: 36px;
  padding: 0 16px; border-radius: 6px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent;
}
.btn.normal.type_v1 {
  background: linear-gradient(135deg, #6BB6FF, #B89AFF); color: #fff;
}
.btn.normal.type_v1:hover:not(:disabled) { filter: brightness(1.08); }
.btn.normal.type_v1:disabled { background: var(--text-dim); cursor: not-allowed; opacity: .6; }
.btn.normal.type_v2 {
  background: var(--bg-card); color: var(--text); border-color: var(--border);
}
.btn.normal.type_v2:hover:not(:disabled) { background: rgba(107, 182, 255, .1); }
</style>
