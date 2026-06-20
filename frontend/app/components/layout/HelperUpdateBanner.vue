<template>
  <Transition name="slide-down">
    <div v-if="visible" class="banner">
      <div class="banner-inner">
        <span class="banner-icon">⬆︎</span>
        <span class="banner-text">
          helper 업데이트 가능 — 현재
          <strong>{{ helperVersion.running || '?' }}</strong> → 최신
          <strong>{{ helperVersion.latest }}</strong>
        </span>
        <div class="banner-actions">
          <NuxtLink to="/helper-install" class="btn-update">지금 업데이트</NuxtLink>
          <button type="button" class="btn-dismiss" @click="dismiss">닫기</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { useHelperVersionStore } from '~/stores/helperVersion';

const helperVersion = useHelperVersionStore();
const dismissed = useState<string>('helper-update-dismissed', () => '');

/** 같은 latest 버전 한 번 닫으면 그 세션 동안 다시 안 띄움. 새 버전 나오면 dismissed
 *  값이 옛 것이라 자동으로 다시 표시. */
const visible = computed(() =>
  helperVersion.needsUpdate && dismissed.value !== helperVersion.latest,
);

function dismiss(): void {
  dismissed.value = helperVersion.latest;
}

// SSE 의 helper.version.changed event 받으면 즉시 refresh. backend pod swap 시점에 발사.
// polling 은 fallback — 5분 cycle (SSE 끊긴 경우 backup).
let timer: ReturnType<typeof setInterval> | null = null;
let evtSource: EventSource | null = null;
onMounted(() => {
  void helperVersion.refresh();
  timer = setInterval(() => { void helperVersion.refresh(); }, 5 * 60 * 1000);
  if (typeof window !== 'undefined' && typeof EventSource !== 'undefined') {
    evtSource = new EventSource('/api/messages/events');
    evtSource.addEventListener('helper.version.changed', () => {
      void helperVersion.refresh();
    });
  }
});
onBeforeUnmount(() => {
  if (timer != null) clearInterval(timer);
  evtSource?.close();
  evtSource = null;
});
</script>

<style scoped>
.banner {
  position: fixed; top: 0; left: 0; right: 0;
  z-index: 1050;
  background: #FFF3CD;
  border-bottom: 1px solid #FFD66B;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
}
.banner-inner {
  max-width: 1400px; margin: 0 auto;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 24px;
  font-size: 13px; color: #5C4500;
}
.banner-icon { font-size: 16px; }
.banner-text { flex: 1; }
.banner-text strong { font-weight: 700; color: #3D2D00; }
.banner-actions { display: flex; gap: 8px; }
.btn-update {
  height: 28px; padding: 0 12px;
  background: #0062ff; color: #fff;
  border-radius: 4px; font-size: 12px; font-weight: 600;
  text-decoration: none;
  display: inline-flex; align-items: center;
}
.btn-update:hover { background: #0052d4; }
.btn-dismiss {
  height: 28px; padding: 0 10px;
  background: transparent; color: #5C4500;
  border: 1px solid #D4B650; border-radius: 4px;
  font-size: 12px; cursor: pointer;
}
.btn-dismiss:hover { background: rgba(212, 182, 80, 0.15); }
.slide-down-enter-active, .slide-down-leave-active {
  transition: transform .25s ease, opacity .25s ease;
}
.slide-down-enter-from, .slide-down-leave-to {
  transform: translateY(-100%); opacity: 0;
}
</style>
