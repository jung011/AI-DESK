<template>
  <div class="local-resource" :class="{ critical: anyHigh }">
    <div class="row">
      <div class="metric" :title="daemonTip">
        <div class="metric-label">
          옛 mcp daemon 누적
          <span class="tag tag-cleanup">정리로 즉시 0%</span>
        </div>
        <div class="metric-bar">
          <div class="metric-fill" :class="levelOf(daemonPct)" :style="{ width: barWidth(daemonPct) }" />
        </div>
        <div class="metric-pct" :class="levelOf(daemonPct)">{{ pctLabel(daemonPct) }}</div>
      </div>
      <div class="action">
        <button
          class="btn-cleanup"
          :disabled="loading || (status?.staleDaemonCount ?? 0) === 0"
          :title="(status?.staleDaemonCount ?? 0) === 0 ? '정리할 옛 daemon 이 없습니다' : `옛 mcp daemon ${status?.staleDaemonCount}개 정리`"
          @click="openConfirm">
          {{ loading ? '정리 중…' : '정리' }}
        </button>
      </div>
    </div>

    <!-- 결과 inline 표시 -->
    <div v-if="result" class="result-inline">
      <span class="result-text">{{ resultMessage }}</span>
      <button class="btn-close" @click="result = null">×</button>
    </div>

    <!-- confirm modal -->
    <div v-if="confirmOpen" class="modal-backdrop" @click.self="confirmOpen = false">
      <div class="modal">
        <h3>리소스 정리 실행</h3>
        <p class="modal-body">
          옛 mcp daemon <b>{{ status?.staleDaemonCount }}개</b> 를 종료합니다.
        </p>
        <p class="modal-hint">
          ⚠️ 현재 작업 중인 claude code 의 자식 mcp daemon 도 같이 종료될 수 있어요.
          정상 path 에선 claude code 가 자동 재spawn 합니다.
        </p>
        <div class="modal-actions">
          <button class="btn-ghost" @click="confirmOpen = false">취소</button>
          <button class="btn-primary" @click="runCleanup">정리 실행</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 옛 mcp daemon 누적 모니터 + 정리 도구 — 대시보드 단일 위치.
 *
 * 옛엔 macOS uptime% 게이지도 같이 있었으나 helper proxy 패턴 ([[project-helper-proxy-pattern]])
 * 적용 후 *uptime 누적 사고 가능성 현저히 적어* daily UX 의 *과한 권고 차단* 제거.
 * 진단 필요 시 resource-cleanup 페이지에서 uptime + 추이 그래프 그대로 확인.
 *
 * helper /api/system/status + /api/cleanup 사용.
 */
interface SystemStatus {
  uptimeSeconds: number | null;
  uptimeDays: number | null;
  staleDaemonCount: number;
  staleDaemons: Array<{ pid: number; etime: string; command: string }>;
  restartRecommended: boolean;
}

interface CleanupResult {
  kill: {
    killedPids: number[];
    failed: Array<{ pid: number; reason: string }>;
    totalFound: number;
  };
  status: SystemStatus;
}

const DAEMON_FULL_COUNT = 10;

const status = ref<SystemStatus | null>(null);
const loading = ref(false);
const confirmOpen = ref(false);
const result = ref<CleanupResult | null>(null);

const daemonPct = computed(() => {
  const c = status.value?.staleDaemonCount;
  if (c == null) return -1;
  return Math.round(Math.min(100, (c / DAEMON_FULL_COUNT) * 100));
});
const daemonTip = computed(() => {
  const c = status.value?.staleDaemonCount;
  if (c == null) return 'daemon 갯수 확인 불가';
  return `옛 mcp daemon ${c}개. ${DAEMON_FULL_COUNT}개 = 100%`;
});
const anyHigh = computed(() => daemonPct.value >= 80);

const resultMessage = computed(() => {
  if (!result.value) return '';
  const r = result.value.kill;
  if (r.killedPids.length > 0) {
    return `✓ daemon ${r.killedPids.length}개 종료 완료 (pid: ${r.killedPids.join(', ')})`;
  }
  if (r.totalFound === 0) {
    return '정리할 옛 daemon 이 없었습니다.';
  }
  return `daemon ${r.totalFound}개 발견 — 종료 실패 ${r.failed.length}개`;
});

function levelOf(pct: number): 'low' | 'mid' | 'high' | 'na' {
  if (pct < 0) return 'na';
  if (pct >= 80) return 'high';
  if (pct >= 50) return 'mid';
  return 'low';
}
function barWidth(pct: number): string {
  return Math.max(0, Math.min(100, pct < 0 ? 0 : pct)) + '%';
}
function pctLabel(pct: number): string {
  return pct < 0 ? '—' : pct + '%';
}

function openConfirm(): void {
  if ((status.value?.staleDaemonCount ?? 0) === 0) return;
  confirmOpen.value = true;
}

async function runCleanup(): Promise<void> {
  if (loading.value) return;
  confirmOpen.value = false;
  loading.value = true;
  try {
    const { $helper } = useNuxtApp();
    result.value = await $helper<CleanupResult>('/api/cleanup', {
      method: 'POST',
      body: { flushDns: false },
    });
    if (result.value?.status) status.value = result.value.status;
  } catch (e: unknown) {
    // eslint-disable-next-line no-alert
    alert(`정리 실패: ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    loading.value = false;
  }
}

let timer: ReturnType<typeof setInterval> | null = null;
async function fetchOnce(): Promise<void> {
  try {
    const { $helper } = useNuxtApp();
    status.value = await $helper<SystemStatus>('/api/system/status');
  } catch {
    // helper 미가동 / 옛 helper (endpoint 없음). 다음 폴링 재시도.
  }
}
onMounted(() => {
  void fetchOnce();
  timer = setInterval(fetchOnce, 60_000);
});
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.local-resource {
  background: var(--bg-card);
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  transition: border-color .15s, background .15s;
}
.local-resource.critical { border-color: #FFB454; background: rgba(255, 180, 84, 0.05); }

.row {
  display: grid; gap: 18px; align-items: end;
  grid-template-columns: 1fr auto;
}
.metric { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.metric-label {
  font-size: 11px; font-weight: 600; color: #475569;
  display: flex; align-items: center; gap: 6px;
}
.tag {
  font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 3px;
  letter-spacing: .02em;
}
.tag-restart { background: #FEE2E2; color: #B91C1C; }
.tag-cleanup { background: #DCFCE7; color: #166534; }

.metric-bar { height: 6px; background: #F1F5F9; border-radius: 4px; overflow: hidden; }
.metric-fill { height: 100%; border-radius: 4px; transition: width .3s, background .3s; }
.metric-fill.low  { background: #00C853; }
.metric-fill.mid  { background: #FFB300; }
.metric-fill.high { background: #E53935; }
.metric-fill.na   { background: #CBD5E1; }

.metric-pct {
  font-size: 12px; font-weight: 700;
  text-align: right;
}
.metric-pct.low  { color: #2E7D32; }
.metric-pct.mid  { color: #E65100; }
.metric-pct.high { color: #E53935; }
.metric-pct.na   { color: #94A3B8; }

.action { display: flex; align-items: center; padding-bottom: 6px; }
.btn-cleanup {
  background: #475569; color: #fff;
  border: none; border-radius: 6px;
  padding: 8px 14px;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
  transition: background .12s;
  white-space: nowrap;
}
.btn-cleanup:hover:not(:disabled) { background: #334155; }
.btn-cleanup:disabled { background: #CBD5E1; cursor: not-allowed; }

.result-inline {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 10px;
  padding: 8px 10px;
  background: #F0FDF4;
  border-left: 3px solid #22C55E;
  border-radius: 4px;
}
.result-text { font-size: 12px; color: #166534; }
.btn-close {
  background: transparent; border: none; cursor: pointer;
  font-size: 16px; color: #6B7785;
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
}
.btn-close:hover { color: #1F2937; }

/* ─── modal ─── */
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--bg-card);
  border-radius: 10px;
  padding: 24px;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 10px 40px rgba(0,0,0,0.2);
}
.modal h3 { margin: 0 0 12px; font-size: 16px; font-weight: 700; color: #1F2937; }
.modal-body { font-size: 13px; color: #374151; margin: 0 0 8px; }
.modal-body b { color: #B91C1C; }
.modal-hint {
  font-size: 12px; color: #6B7785;
  margin: 6px 0;
  padding: 6px 10px;
  background: #F9FAFB;
  border-left: 2px solid #FFB454;
  border-radius: 3px;
}
.modal-hint b { color: #1F2937; }
.modal-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 16px;
}
.btn-ghost {
  background: transparent;
  border: 1px solid #D1D5DB;
  color: #6B7785;
  border-radius: 6px;
  padding: 8px 16px;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
}
.btn-ghost:hover { background: #F9FAFB; color: #1F2937; }
.btn-primary {
  background: #475569; color: #fff;
  border: none; border-radius: 6px;
  padding: 8px 16px;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
}
.btn-primary:hover { background: #334155; }
</style>
