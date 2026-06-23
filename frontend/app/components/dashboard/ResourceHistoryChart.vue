<template>
  <section class="chart-card">
    <div class="card-head">
      <h2>시간 추이 (최근 24시간)</h2>
      <span class="muted">{{ samples.length }} samples · 1분 간격</span>
    </div>
    <div v-if="samples.length < 2" class="placeholder">
      적재된 데이터가 부족합니다 (helper 시작 후 약 2분 경과 필요).
    </div>
    <div v-else class="chart-stack">
      <!-- macOS uptime % chart -->
      <div class="chart-row">
        <div class="chart-label">
          macOS uptime % <span class="tag tag-restart">재부팅만 해결</span>
        </div>
        <svg :viewBox="`0 0 ${SVG_W} ${SVG_H}`" class="chart-svg">
          <!-- 임계 line (80%) -->
          <line :x1="0" :y1="lineY(80)" :x2="SVG_W" :y2="lineY(80)" class="threshold-line" />
          <text :x="SVG_W - 4" :y="lineY(80) - 4" class="threshold-label">80%</text>
          <!-- area -->
          <path :d="areaPath(uptimePcts)" class="area-uptime" />
          <!-- line -->
          <path :d="linePath(uptimePcts)" class="line-uptime" />
          <!-- 마지막 점 -->
          <circle :cx="lastX(uptimePcts)" :cy="lastY(uptimePcts)" r="3" class="dot-uptime" />
        </svg>
        <div class="chart-stats">
          <span>현재 <b :class="levelOf(uptimeNow)">{{ uptimeNow }}%</b></span>
          <span class="muted">최근 24h 최대 {{ uptimeMax }}%</span>
        </div>
      </div>

      <!-- daemon 누적 % chart -->
      <div class="chart-row">
        <div class="chart-label">
          옛 mcp daemon 누적 % <span class="tag tag-cleanup">정리로 즉시 0%</span>
        </div>
        <svg :viewBox="`0 0 ${SVG_W} ${SVG_H}`" class="chart-svg">
          <line :x1="0" :y1="lineY(80)" :x2="SVG_W" :y2="lineY(80)" class="threshold-line" />
          <text :x="SVG_W - 4" :y="lineY(80) - 4" class="threshold-label">80%</text>
          <path :d="areaPath(daemonPcts)" class="area-daemon" />
          <path :d="linePath(daemonPcts)" class="line-daemon" />
          <circle :cx="lastX(daemonPcts)" :cy="lastY(daemonPcts)" r="3" class="dot-daemon" />
        </svg>
        <div class="chart-stats">
          <span>현재 <b :class="levelOf(daemonNow)">{{ daemonNow }}%</b></span>
          <span class="muted">최근 24h 최대 {{ daemonMax }}%</span>
        </div>
      </div>

      <!-- x-axis label -->
      <div class="x-axis">
        <span>{{ formatTime(samples[0]?.t) }}</span>
        <span class="muted">← 24h ago</span>
        <span class="muted">now →</span>
        <span>{{ formatTime(samples[samples.length - 1]?.t) }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
interface Sample { t: number; uptimeSec: number | null; daemonCount: number }

const UPTIME_FULL_DAYS = 14;
const DAEMON_FULL_COUNT = 10;
const SVG_W = 800;
const SVG_H = 80;

const samples = ref<Sample[]>([]);

const uptimePcts = computed(() => samples.value.map(s => {
  if (s.uptimeSec == null) return -1;
  return Math.min(100, (s.uptimeSec / 86400 / UPTIME_FULL_DAYS) * 100);
}));
const daemonPcts = computed(() => samples.value.map(s =>
  Math.min(100, (s.daemonCount / DAEMON_FULL_COUNT) * 100)
));

const uptimeNow = computed(() => Math.round(uptimePcts.value[uptimePcts.value.length - 1] ?? 0));
const daemonNow = computed(() => Math.round(daemonPcts.value[daemonPcts.value.length - 1] ?? 0));
const uptimeMax = computed(() => Math.round(Math.max(0, ...uptimePcts.value.filter(p => p >= 0))));
const daemonMax = computed(() => Math.round(Math.max(0, ...daemonPcts.value)));

function lineY(pct: number): number {
  // SVG y = 0 이 위. pct 100 → y 0, pct 0 → y SVG_H
  return SVG_H - (pct / 100) * SVG_H;
}
function pointX(idx: number, total: number): number {
  if (total <= 1) return 0;
  return (idx / (total - 1)) * SVG_W;
}

function linePath(pcts: number[]): string {
  if (pcts.length === 0) return '';
  const points = pcts.map((p, i) => `${pointX(i, pcts.length).toFixed(1)},${lineY(p < 0 ? 0 : p).toFixed(1)}`);
  return 'M' + points.join(' L');
}
function areaPath(pcts: number[]): string {
  if (pcts.length === 0) return '';
  const points = pcts.map((p, i) => `${pointX(i, pcts.length).toFixed(1)},${lineY(p < 0 ? 0 : p).toFixed(1)}`);
  return `M0,${SVG_H} L${points.join(' L')} L${SVG_W},${SVG_H} Z`;
}
function lastX(pcts: number[]): number { return pointX(pcts.length - 1, pcts.length); }
function lastY(pcts: number[]): number {
  const last = pcts[pcts.length - 1] ?? 0;
  return lineY(last < 0 ? 0 : last);
}

function levelOf(pct: number): 'low' | 'mid' | 'high' | 'na' {
  if (pct < 0) return 'na';
  if (pct >= 80) return 'high';
  if (pct >= 50) return 'mid';
  return 'low';
}

function formatTime(ts: number | undefined): string {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

let timer: ReturnType<typeof setInterval> | null = null;
async function fetchHistory(): Promise<void> {
  try {
    const { $helper } = useNuxtApp();
    const data = await $helper<{ samples: Sample[] }>('/api/system/status-history');
    samples.value = data?.samples ?? [];
  } catch {
    samples.value = [];
  }
}
onMounted(() => {
  void fetchHistory();
  // 60s 마다 history 갱신 (helper sampler 와 동일 주기)
  timer = setInterval(fetchHistory, 60_000);
});
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<style scoped>
.chart-card {
  background: rgba(15, 23, 41, 0.6);
  border: 1px solid #1E2738;
  border-radius: 12px;
  padding: 18px 20px;
  color: #E5E9EE;
}
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.card-head h2 { font-size: 14px; font-weight: 600; margin: 0; color: #B7C2D0; }
.muted { font-size: 12px; color: #6B7785; }

.placeholder { font-size: 13px; color: #6B7785; padding: 24px 0; text-align: center; }

.chart-stack { display: flex; flex-direction: column; gap: 16px; }
.chart-row { display: flex; flex-direction: column; gap: 6px; }
.chart-label {
  font-size: 12px; font-weight: 600; color: #94A3B8;
  display: flex; align-items: center; gap: 8px;
}
.tag {
  font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 3px;
}
.tag-restart { background: rgba(229, 57, 53, 0.18); color: #FCA5A5; }
.tag-cleanup { background: rgba(0, 200, 83, 0.18); color: #86EFAC; }

.chart-svg {
  width: 100%; height: 80px;
  background: rgba(255,255,255,0.02);
  border-radius: 4px;
}

.threshold-line {
  stroke: rgba(255, 180, 84, 0.4);
  stroke-width: 1;
  stroke-dasharray: 4 4;
}
.threshold-label {
  font-size: 9px;
  fill: rgba(255, 180, 84, 0.6);
  text-anchor: end;
}

.area-uptime { fill: rgba(255, 99, 99, 0.18); }
.line-uptime { stroke: #FF6B6B; stroke-width: 1.5; fill: none; }
.dot-uptime { fill: #FF6B6B; }

.area-daemon { fill: rgba(107, 182, 255, 0.18); }
.line-daemon { stroke: #6BB6FF; stroke-width: 1.5; fill: none; }
.dot-daemon { fill: #6BB6FF; }

.chart-stats {
  display: flex; gap: 14px;
  font-size: 12px; color: #94A3B8;
}
.chart-stats b { color: #E5E9EE; font-weight: 700; }
.chart-stats b.low { color: #00C853; }
.chart-stats b.mid { color: #FFB300; }
.chart-stats b.high { color: #E53935; }

.x-axis {
  display: flex; justify-content: space-between;
  font-size: 11px; color: #6B7785;
  padding-top: 6px;
  border-top: 1px dashed #1E2738;
}
</style>
