<template>
  <Teleport to="body">
    <div v-if="open" class="popup-overlay" @click.self="emit('cancel')">
      <div class="popup-box" role="alertdialog">
        <header class="popup-head">
          <h3>{{ title }}</h3>
        </header>
        <div class="popup-body">
          <p>{{ message }}</p>
          <!-- 선택 사항 — 호출자가 extraOptionLabel 을 넘기면 체크박스 노출 -->
          <label v-if="extraOptionLabel" class="extra-option">
            <input
              type="checkbox"
              :checked="extraOption"
              :disabled="busy"
              @change="extraOption = ($event.target as HTMLInputElement).checked" />
            <span>{{ extraOptionLabel }}</span>
          </label>
        </div>
        <footer class="popup-foot">
          <button class="btn normal type_v2" type="button" :disabled="busy" @click="emit('cancel')">
            {{ cancelLabel }}
          </button>
          <button
            class="btn normal"
            :class="destructive ? 'type_v6' : 'type_v1'"
            type="button"
            :disabled="busy"
            @click="emit('confirm', { extraOption })">
            {{ busy ? '처리 중…' : confirmLabel }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  /** 본문 아래 체크박스 라벨. 비어있으면 체크박스 미노출. */
  extraOptionLabel?: string;
  /** 체크박스 초기값. 기본 true. */
  extraOptionDefault?: boolean;
}>(), {
  confirmLabel: '확인',
  cancelLabel: '취소',
  destructive: false,
  busy: false,
  extraOptionLabel: '',
  extraOptionDefault: true,
});

const emit = defineEmits<{
  (e: 'confirm', payload: { extraOption: boolean }): void;
  (e: 'cancel'): void;
}>();

/** 다이얼로그가 새로 열릴 때마다 체크박스 상태 리셋. */
const extraOption = ref(props.extraOptionDefault);
watch(() => props.open, (v) => {
  if (v) extraOption.value = props.extraOptionDefault;
});
</script>

<style scoped>
.popup-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100;
  backdrop-filter: blur(2px);
}
.popup-box {
  width: 380px; max-width: calc(100vw - 40px);
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, .55);
  display: flex; flex-direction: column;
}
.popup-head { padding: 16px 20px; border-bottom: 1px solid var(--border); }
.popup-head h3 { font-size: 15px; font-weight: 700; color: #FFFFFF; margin: 0; }
.popup-body { padding: 20px; }
.popup-body p {
  margin: 0; color: #E5EBF5; font-size: 13px; line-height: 1.6;
  white-space: pre-line;  /* message 의 \n 을 줄바꿈으로 렌더 */
}
.extra-option {
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px; padding-top: 12px;
  border-top: 1px solid var(--border);
  font-size: 12px; color: #B0BCD0;
  cursor: pointer; user-select: none;
}
/* 전역 reset 이 input 의 appearance/사이즈를 0 으로 꺼놨기 때문에 복구 — 브라우저 기본 체크박스 사용. */
.extra-option input[type=checkbox] {
  appearance: auto;
  -webkit-appearance: auto;
  width: 14px; height: 14px;
  margin: 0;
  cursor: pointer;
  accent-color: #6BB6FF;
}
.extra-option:has(input:disabled) { cursor: not-allowed; opacity: .6; }
.popup-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 20px; border-top: 1px solid var(--border);
}
.btn.normal {
  display: inline-flex; align-items: center; height: 36px;
  padding: 0 16px; border-radius: 6px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent;
}
.btn.normal.type_v1 { background: linear-gradient(135deg, #6BB6FF, #B89AFF); color: #fff; }
.btn.normal.type_v1:hover:not(:disabled) { filter: brightness(1.1); }
.btn.normal.type_v6 { background: #E25555; color: #fff; }
.btn.normal.type_v6:hover:not(:disabled) { background: #CF4444; }
.btn.normal.type_v2 {
  background: var(--bg-input); color: #E5EBF5; border-color: var(--border);
}
.btn.normal.type_v2:hover:not(:disabled) { background: rgba(107, 182, 255, 0.1); border-color: #6BB6FF; }
.btn.normal:disabled { opacity: .6; cursor: not-allowed; }
</style>
