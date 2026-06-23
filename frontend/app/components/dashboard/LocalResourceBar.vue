<template>
  <NuxtLink to="/resource-cleanup" class="local-resource" :class="{ critical: anyHigh }">
    <div class="row">
      <div class="metric" :title="uptimeTip">
        <div class="metric-label">
          macOS uptime
          <span class="tag tag-restart">재부팅만 해결</span>
        </div>
        <div class="metric-bar">
          <div class="metric-fill" :class="levelOf(uptimePct)" :style="{ width: barWidth(uptimePct) }" />
        </div>
        <div class="metric-pct" :class="levelOf(uptimePct)">{{ pctLabel(uptimePct) }}</div>
      </div>
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
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">
/**
 * 리소스 누적 모니터 — 사용자가 100% 도달 전 재부팅 시점 판단.
 *
 * uptime% = kernel state 누적 지표. cleanup 으로 *안 줄어듦* → 재부팅만 답.
 * daemon% = process 잔재 지표. cleanup 으로 즉시 0% 가능.
 *
 * helper /api/system/status 의 uptimeSeconds + staleDaemonCount 사용.
 */
interface SystemStatus {
  uptimeSeconds: number | null;
  uptimeDays: number | null;
  staleDaemonCount: number;
  restartRecommended: boolean;
}

const UPTIME_FULL_DAYS = 14;
const DAEMON_FULL_COUNT = 10;

const status = ref<SystemStatus | null>(null);

const uptimePct = computed(() => {
  const d = status.value?.uptimeDays;
  if (d == null) return -1;
  return Math.round(Math.min(100, (d / UPTIME_FULL_DAYS) * 100));
});

const daemonPct = computed(() => {
  const c = status.value?.staleDaemonCount;
  if (c == null) return -1;
  return Math.round(Math.min(100, (c / DAEMON_FULL_COUNT) * 100));
});

const uptimeTip = computed(() => {
  const d = status.value?.uptimeDays;
  if (d == null) return 'uptime 확인 불가';
  return `재부팅 후 ${d.toFixed(1)}일 경과. ${UPTIME_FULL_DAYS}일 = 100%`;
});
const daemonTip = computed(() => {
  const c = status.value?.staleDaemonCount;
  if (c == null) return 'daemon 갯수 확인 불가';
  return `옛 mcp daemon ${c}개. ${DAEMON_FULL_COUNT}개 = 100%. 클릭 → 리소스 정리`;
});

const anyHigh = computed(() => uptimePct.value >= 80 || daemonPct.value >= 80);

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
  display: block;
  text-decoration: none;
  background: #fff;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  transition: border-color .15s, background .15s;
}
.local-resource:hover { border-color: #93C5FD; background: #F8FAFC; }
.local-resource.critical { border-color: #FFB454; background: rgba(255, 180, 84, 0.05); }

.row {
  display: grid; gap: 18px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}
.metric { display: flex; flex-direction: column; gap: 5px; }
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
</style>
