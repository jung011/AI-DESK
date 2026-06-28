<template>
  <Teleport to="body">
    <div v-if="open" class="popup-overlay" @click.self="onCancel">
      <div class="popup-box" role="dialog">
        <header class="popup-head">
          <h3>
            {{ meAgentMissing
                 ? '(me) 워크스페이스 재지정'
                 : (savedPath ? '(me) 워크스페이스 변경' : '(me) 워크스페이스 지정') }}
          </h3>
        </header>
        <div class="popup-body">
          <p v-if="meAgentMissing" class="warn">
            (me) AI 카드가 사라진 상태입니다. 아래 폴더로 다시 저장하거나 다른 폴더를 선택해
            (me) 를 복원하세요.
          </p>
          <p class="desc">
            본인 mac 의 *주 작업 폴더* 를 지정하세요. 그 폴더의 claude 가 본인의 (me) AI 로
            동작하며, 사내 동료들이 보낸 메시지를 받게 됩니다. 지정 후 대시보드에 (me) 카드가
            등장합니다.
          </p>
          <div class="path-row">
            <span class="path-value" :class="{ unset: !path }">
              {{ path || '미지정 — 폴더를 선택하세요' }}
            </span>
            <button
              type="button"
              class="btn-secondary"
              :disabled="picking || saving"
              @click="onBrowse">
              {{ picking ? '선택 중…' : '폴더 선택' }}
            </button>
          </div>
          <!-- 옛 워크스페이스가 있고 새 path 가 다를 때만 노출 — 신규 지정/재지정 모드엔 의미 X. -->
          <label v-if="showPurgeOption" class="purge-option">
            <input
              type="checkbox"
              :checked="purgePreviousHistory"
              :disabled="saving"
              @change="purgePreviousHistory = ($event.target as HTMLInputElement).checked" />
            <span>기존 워크스페이스의 Claude 대화 기록도 함께 삭제</span>
          </label>
          <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
        </div>
        <footer class="popup-foot">
          <button
            class="btn normal type_v2"
            type="button"
            :disabled="saving"
            @click="onCancel">
            {{ savedPath ? '취소' : '나중에' }}
          </button>
          <button
            class="btn normal type_v1"
            type="button"
            :disabled="!path || saving || (path === savedPath && !meAgentMissing)"
            @click="onSave">
            {{ saving ? '저장 중…' : '저장' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface A2aWorkspaceRs { path: string }
interface HelperBrowseRs { rc: number; path?: string; message?: string }
interface HelperScopeRs { rc: number; message?: string; absolutePath?: string }

const props = withDefaults(defineProps<{
  open: boolean;
  /** 현재 저장된 경로 (없으면 빈 문자열). 다이얼로그가 열릴 때 현재값을 표시한다. */
  initialPath?: string;
  /** 설정 path 는 있지만 t_ai_agent 의 (me) row 가 사라진 비정상 상태. 같은 path 로
   *  다시 저장하기만 해도 (me) 복원되도록 저장 버튼 활성화 조건을 완화한다. */
  meAgentMissing?: boolean;
}>(), {
  initialPath: '',
  meAgentMissing: false,
});

const emit = defineEmits<{
  (e: 'saved', path: string): void;
  (e: 'cancel'): void;
}>();

const path = ref('');
const savedPath = ref('');
const picking = ref(false);
const saving = ref(false);
const errorMsg = ref('');
/** 변경 모드(옛 path 가 있고 새 path 가 다름)에서만 의미 있음. AI 삭제 다이얼로그와
 *  동일 패턴으로 default true. */
const purgePreviousHistory = ref(true);

/** 신규 지정 / 같은 폴더 재지정 모드엔 옛 워크스페이스가 없으므로 옵션 숨김. */
const showPurgeOption = computed(
  () => !!savedPath.value && savedPath.value !== path.value,
);

watch(() => props.open, (next) => {
  if (next) {
    path.value = props.initialPath || '';
    savedPath.value = props.initialPath || '';
    picking.value = false;
    saving.value = false;
    errorMsg.value = '';
    purgePreviousHistory.value = true;
  }
});

async function onBrowse(): Promise<void> {
  if (picking.value) return;
  picking.value = true;
  errorMsg.value = '';
  try {
    const { $helper } = useNuxtApp();
    const res = await $helper<HelperBrowseRs>('/api/browse-workspace', {
      method: 'POST',
    });
    if (res.rc !== 0) {
      errorMsg.value = res.message || '폴더 선택을 사용할 수 없습니다.';
      return;
    }
    if (res.path) path.value = res.path;
  } catch (e) {
    errorMsg.value = `폴더 선택 호출 실패 (helper 가동 확인): ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    picking.value = false;
  }
}

async function onSave(): Promise<void> {
  if (saving.value || !path.value) return;
  saving.value = true;
  errorMsg.value = '';
  try {
    // 1단계: 본인 mac 의 helper 에 scope-workspace 요청 — 폴더 검증 + ~/.claude.json
    // scope 처리 + 절대 경로 정규화. 멀티 mac 환경에서 backend 가 사용자 mac 의 helper
    // 에 접근할 수 없으므로, brower 가 본인 localhost helper 를 직접 호출한다.
    const { $helper, $api } = useNuxtApp();
    const scope = await $helper<HelperScopeRs>('/api/scope-workspace', {
      method: 'POST',
      body: {
        newWorkspace: path.value,
        oldWorkspace: savedPath.value,
        // showPurgeOption 가 false 일 땐 사용자 입력이 무의미하므로 false 로 전달.
        purgePreviousHistory: showPurgeOption.value && purgePreviousHistory.value,
        meTmuxSession: '',
      },
    });
    if (scope.rc !== 0) {
      errorMsg.value = mapScopeError(scope.rc, scope.message);
      return;
    }
    const absolute = scope.absolutePath || path.value;
    // 2단계: backend 에 검증된 path 만 전달 — DB 저장 + (me) row upsert.
    const env = await $api<ApiEnvelope<A2aWorkspaceRs>>('/api/settings/a2a-workspace', {
      method: 'PUT',
      body: { path: absolute, purgePreviousHistory: false },
    });
    if (env.result === 0 && env.data) {
      emit('saved', env.data.path || absolute);
    } else {
      errorMsg.value = env.message || '저장 실패';
    }
  } catch (e) {
    errorMsg.value = `저장 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    saving.value = false;
  }
}

function mapScopeError(rc: number, message?: string): string {
  switch (rc) {
    case 1: return '경로가 비어 있습니다.';
    case 2: return '존재하지 않거나 디렉토리가 아닙니다.';
    case 3: return '~/.claude.json 갱신에 실패했습니다.';
    default: return message || `폴더 검증 실패 (rc=${rc})`;
  }
}

function onCancel(): void {
  if (saving.value) return;
  emit('cancel');
}
</script>

<style scoped>
.popup-overlay {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100;
}
.popup-box {
  width: 460px; max-width: calc(100vw - 40px);
  background: var(--bg-card); border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
  display: flex; flex-direction: column;
}
.popup-head { padding: 16px 20px; border-bottom: 1px solid #F0F2F5; }
.popup-head h3 { font-size: 15px; font-weight: 700; color: #101010; margin: 0; }
.popup-body { padding: 20px; }
.desc {
  margin: 0 0 14px;
  font-size: 12px; color: #475569; line-height: 1.6;
}
.warn {
  margin: 0 0 12px;
  padding: 10px 12px;
  background: #FFF7E6; border: 1px solid #FFD591;
  border-radius: 6px;
  font-size: 12px; color: #8B5A1A; line-height: 1.5;
}
.path-row {
  display: flex; align-items: center; gap: 10px;
}
.path-value {
  flex: 1;
  padding: 10px 14px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
  color: #1E293B;
  word-break: break-all;
}
.path-value.unset { color: #94A3B8; font-family: inherit; font-style: italic; }
.purge-option {
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px; padding-top: 12px;
  border-top: 1px solid #F0F2F5;
  font-size: 12px; color: #475569;
  cursor: pointer; user-select: none;
}
.purge-option input[type=checkbox] {
  appearance: auto;
  -webkit-appearance: auto;
  width: 14px; height: 14px;
  margin: 0;
  cursor: pointer;
  accent-color: #0062ff;
}
.purge-option:has(input:disabled) { cursor: not-allowed; opacity: .6; }
.btn-secondary {
  height: 36px; padding: 0 16px;
  background: var(--bg-card); color: #475569;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  white-space: nowrap;
}
.btn-secondary:hover:not(:disabled) { background: #F8FAFC; border-color: #0062ff; color: #0062ff; }
.btn-secondary:disabled { opacity: .6; cursor: not-allowed; }
.error-msg {
  margin: 12px 0 0;
  padding: 8px 12px;
  background: #FFE5E9; border: 1px solid #FFB4BD;
  border-radius: 6px;
  font-size: 12px; color: #B22B45;
}
.popup-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 20px; border-top: 1px solid #F0F2F5;
}
.btn.normal {
  display: inline-flex; align-items: center; height: 36px;
  padding: 0 16px; border-radius: 6px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent;
}
.btn.normal.type_v1 { background: #0062ff; color: #fff; }
.btn.normal.type_v1:hover:not(:disabled) { background: #0052d4; }
.btn.normal.type_v2 {
  background: var(--bg-card); color: #475569; border-color: #D4DCE4;
}
.btn.normal.type_v2:hover:not(:disabled) { background: #F8FAFC; }
.btn.normal:disabled { opacity: .6; cursor: not-allowed; }
</style>
