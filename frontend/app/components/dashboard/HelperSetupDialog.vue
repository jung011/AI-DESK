<template>
  <Teleport to="body">
    <div v-if="open" class="popup-overlay" @click.self="onCancel">
      <div class="popup-box" role="dialog">
        <header class="popup-head">
          <h3>중앙서버 연결 설정</h3>
        </header>
        <div class="popup-body">
          <p class="desc">
            본 mac 의 helper 가 가리키는 중앙서버 URL 이 현재 페이지와 다릅니다.
            <br />helper 를 *현재 페이지의 중앙서버* 로 갱신할까요?
          </p>
          <table class="kv">
            <tbody>
              <tr>
                <th>helper 가 가리키는 곳</th>
                <td class="mono">{{ currentBackendUrl || '(미설정 — localhost:30081)' }}</td>
              </tr>
              <tr>
                <th>현재 페이지 (새 hub)</th>
                <td class="mono">{{ pageOrigin }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
        </div>
        <footer class="popup-foot">
          <button class="btn normal type_v2" type="button" :disabled="saving" @click="onCancel">
            나중에
          </button>
          <button class="btn normal type_v1" type="button" :disabled="saving" @click="onConfirm">
            {{ saving ? '갱신 중…' : '갱신하기' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
interface HelperSetupRs { rc: number; message?: string; currentBackendUrl?: string }

const props = defineProps<{
  open: boolean;
  currentBackendUrl: string;
  pageOrigin: string;
}>();

const emit = defineEmits<{
  (e: 'applied'): void;
  (e: 'cancel'): void;
}>();

const saving = ref(false);
const errorMsg = ref('');

watch(() => props.open, (v) => {
  if (v) {
    saving.value = false;
    errorMsg.value = '';
  }
});

async function onConfirm(): Promise<void> {
  if (saving.value) return;
  saving.value = true;
  errorMsg.value = '';
  try {
    const { $helper } = useNuxtApp();
    const res = await $helper<HelperSetupRs>('/api/setup', {
      method: 'POST',
      body: { hubUrl: props.pageOrigin },
    });
    if (res.rc !== 0) {
      errorMsg.value = res.message || '설정 갱신 실패';
      return;
    }
    emit('applied');
    // helper 가 0.5s 후 launchctl bootout + bootstrap. brower 도 3s 뒤 새로고침.
    setTimeout(() => { window.location.reload(); }, 3000);
  } catch (e) {
    errorMsg.value = `helper 호출 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    saving.value = false;
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
  z-index: 1200;
}
.popup-box {
  width: 480px; max-width: calc(100vw - 40px);
  background: var(--bg-card); border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
}
.popup-head { padding: 16px 20px; border-bottom: 1px solid #F0F2F5; }
.popup-head h3 { font-size: 15px; font-weight: 700; color: #101010; margin: 0; }
.popup-body { padding: 20px; }
.desc { margin: 0 0 14px; font-size: 12px; color: #475569; line-height: 1.6; }
.kv { width: 100%; border-collapse: collapse; }
.kv th {
  text-align: left; padding: 8px 12px;
  font-size: 12px; color: #94A3B8; font-weight: 600;
  background: #F8FAFC; border: 1px solid #E2E8F0;
  width: 40%;
}
.kv td {
  padding: 8px 12px; border: 1px solid #E2E8F0;
  font-size: 12px; color: #1E293B;
  word-break: break-all;
}
.mono { font-family: ui-monospace, SFMono-Regular, monospace; }
.error-msg {
  margin: 12px 0 0; padding: 8px 12px;
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
.btn.normal.type_v2 { background: var(--bg-card); color: #475569; border-color: #D4DCE4; }
.btn.normal.type_v2:hover:not(:disabled) { background: #F8FAFC; }
.btn.normal:disabled { opacity: .6; cursor: not-allowed; }
</style>
