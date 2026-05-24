<template>
  <Teleport to="body">
    <div v-if="open" class="popup-overlay" @click.self="emit('cancel')">
      <div class="popup-box" role="dialog">
        <header class="popup-head">
          <h3>터미널 모드 선택</h3>
        </header>
        <div class="popup-body">
          <p class="hint">
            사용자가 종료(exit / Ctrl+C)했거나 아직 한 번도 안 띄운 상태입니다.
            어떤 모드로 claude 를 시작할까요?
          </p>
          <label class="mode-option" :class="{ selected: mode === 'claude' }">
            <input type="radio" value="claude" v-model="mode" />
            <div class="mode-text">
              <div class="mode-title">클로드 (기본)</div>
              <div class="mode-desc">그냥 <code>claude</code> 로 시작</div>
            </div>
          </label>
          <label class="mode-option" :class="{ selected: mode === 'telegram' }">
            <input type="radio" value="telegram" v-model="mode" />
            <div class="mode-text">
              <div class="mode-title">텔레그램</div>
              <div class="mode-desc"><code>claude --channels plugin:telegram@claude-plugins-official</code></div>
            </div>
          </label>
          <label class="mode-option" :class="{ selected: mode === 'custom' }">
            <input type="radio" value="custom" v-model="mode" />
            <div class="mode-text">
              <div class="mode-title">사용자 지정 옵션</div>
              <div class="mode-desc">claude 의 추가 옵션을 직접 입력 (예: <code>--channels plugin:slack@…</code>)</div>
              <input
                v-if="mode === 'custom'"
                v-model="customOpts"
                class="custom-input"
                type="text"
                placeholder="--channels plugin:xxx@…"
                @click.stop
              />
            </div>
          </label>
        </div>
        <footer class="popup-foot">
          <button class="btn normal type_v2" type="button" :disabled="busy" @click="emit('cancel')">취소</button>
          <button
            class="btn normal type_v1"
            type="button"
            :disabled="busy || !canConfirm"
            @click="emit('confirm', { mode, customOpts: mode === 'custom' ? customOpts.trim() : '' })">
            {{ busy ? '시작 중…' : '시작' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  open: boolean;
  busy?: boolean;
}>(), {
  busy: false,
});

const emit = defineEmits<{
  (e: 'confirm', payload: { mode: string; customOpts: string }): void;
  (e: 'cancel'): void;
}>();

const mode = ref<'claude' | 'telegram' | 'custom'>('claude');
const customOpts = ref('');

// 모달이 새로 열릴 때마다 기본값으로 리셋.
watch(() => props.open, (v) => {
  if (v) {
    mode.value = 'claude';
    customOpts.value = '';
  }
});

const canConfirm = computed(() => {
  if (mode.value === 'custom') return customOpts.value.trim().length > 0;
  return true;
});
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
  background: #fff; border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
  display: flex; flex-direction: column;
}
.popup-head { padding: 16px 20px; border-bottom: 1px solid #F0F2F5; }
.popup-head h3 { font-size: 15px; font-weight: 700; color: #101010; margin: 0; }
.popup-body { padding: 20px; display: flex; flex-direction: column; gap: 10px; }
.hint {
  margin: 0 0 6px;
  color: #475569; font-size: 12px; line-height: 1.55;
}
.mode-option {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px;
  border: 1px solid #D4DCE4; border-radius: 8px;
  cursor: pointer;
  transition: border-color .12s, background .12s;
}
.mode-option:hover { border-color: #94A3B8; background: #F8FAFC; }
.mode-option.selected { border-color: #0062ff; background: #EFF6FF; }
/* 전역 reset 보정 — 라디오 버튼 보이게. */
.mode-option input[type=radio] {
  appearance: auto;
  -webkit-appearance: auto;
  width: 14px; height: 14px;
  margin: 3px 0 0;
  cursor: pointer;
  accent-color: #0062ff;
  flex-shrink: 0;
}
.mode-text { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.mode-title { font-size: 13px; font-weight: 600; color: #101010; }
.mode-desc { font-size: 12px; color: #64748B; line-height: 1.4; }
.mode-desc code {
  font-family: ui-monospace, monospace;
  background: #F1F5F9; color: #334155;
  padding: 1px 4px; border-radius: 3px;
  font-size: 11px;
}
.custom-input {
  margin-top: 6px;
  width: 100%; height: 32px;
  padding: 0 10px;
  font-size: 12px; font-family: ui-monospace, monospace;
  background: #fff; color: #101010;
  border: 1px solid #D4DCE4; border-radius: 6px;
  outline: none;
}
.custom-input:focus { border-color: #0062ff; }
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
.btn.normal.type_v2 { background: #fff; color: #475569; border-color: #D4DCE4; }
.btn.normal.type_v2:hover:not(:disabled) { background: #F8FAFC; }
.btn.normal:disabled { opacity: .6; cursor: not-allowed; }
</style>
