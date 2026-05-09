<template>
  <div class="local-usage">
    <!-- 자동 등록됐지만 Claude Code 재시작 대기 -->
    <template v-if="!usage.ready && usage.hookInstalled">
      <div class="local-usage-head">
        <div class="local-usage-title">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/>
          </svg>
          <span>Claude 사용량 — Claude Code 재시작 대기 중</span>
        </div>
      </div>
      <p class="install-help">
        statusLine 이 자동 등록되었습니다. <strong>Claude Code 를 한 번 재시작</strong>하면 5시간 / 컨텍스트 / 주간 사용률이 표시됩니다.
      </p>
    </template>

    <!-- 다른 statusLine 사용 중 — 사용자 결정 필요 -->
    <template v-else-if="!usage.ready && usage.hookOccupiedByOther">
      <div class="local-usage-head">
        <div class="local-usage-title">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/>
          </svg>
          <span>Claude 사용량 — 다른 statusLine 사용 중</span>
        </div>
        <button type="button" class="install-btn" :disabled="installing" @click="onInstall">
          {{ installing ? '교체 중…' : '우리것으로 교체' }}
        </button>
      </div>
      <p class="install-help">
        <code>~/.claude/settings.json</code> 에 이미 다른 <code>statusLine</code> 명령이 설정되어 있어 자동 교체를 보류했습니다.
      </p>
    </template>

    <!-- 자동 설치 자체가 실패한 fallback (드물게 발생) -->
    <template v-else-if="!usage.ready">
      <div class="local-usage-head">
        <div class="local-usage-title">
          <span>Claude 사용량 (자동 등록 실패)</span>
        </div>
        <button type="button" class="install-btn" :disabled="installing" @click="onInstall">
          {{ installing ? '설치 중…' : '수동 설치' }}
        </button>
      </div>
    </template>

    <!-- 설치됨: 정상 표시 -->
    <template v-else>
      <div class="local-usage-row" :title="usage.source">
        <div class="metric">
          <div class="metric-label">5h 세션 사용률<span v-if="resetText" class="reset-hint">· 리셋 {{ resetText }}</span></div>
          <div class="metric-bar">
            <div class="metric-fill" :class="levelOf(usage.fiveHourPct)" :style="{ width: barWidth(usage.fiveHourPct) }" />
          </div>
          <div class="metric-pct" :class="levelOf(usage.fiveHourPct)">{{ pctLabel(usage.fiveHourPct) }}</div>
        </div>
        <div class="metric">
          <div class="metric-label">현재 세션 컨텍스트</div>
          <div class="metric-bar">
            <div class="metric-fill" :class="levelOf(usage.contextPct)" :style="{ width: barWidth(usage.contextPct) }" />
          </div>
          <div class="metric-pct" :class="levelOf(usage.contextPct)">{{ pctLabel(usage.contextPct) }}</div>
        </div>
        <div v-if="usage.weeklyPct >= 0" class="metric">
          <div class="metric-label">주간 사용률</div>
          <div class="metric-bar">
            <div class="metric-fill" :class="levelOf(usage.weeklyPct)" :style="{ width: barWidth(usage.weeklyPct) }" />
          </div>
          <div class="metric-pct" :class="levelOf(usage.weeklyPct)">{{ pctLabel(usage.weeklyPct) }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface LocalUsage {
  fiveHourPct: number;
  fiveHourResetsAt: number;
  weeklyPct: number;
  weeklyResetsAt: number;
  contextPct: number;
  source: string;
  ready: boolean;
  hookInstalled: boolean;
  hookOccupiedByOther: boolean;
}

const usage = ref<LocalUsage>({
  fiveHourPct: -1,
  fiveHourResetsAt: 0,
  weeklyPct: -1,
  weeklyResetsAt: 0,
  contextPct: -1,
  source: '',
  ready: false,
  hookInstalled: false,
  hookOccupiedByOther: false
});

const installing = ref(false);
let timer: ReturnType<typeof setInterval> | null = null;

async function fetchOnce(): Promise<void> {
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<LocalUsage>>('/api/usage/local');
    if (env.result === 0 && env.data) usage.value = env.data;
  } catch {
    /* swallow — 다음 폴링에서 재시도 */
  }
}

async function onInstall(): Promise<void> {
  if (installing.value) return;
  installing.value = true;
  try {
    const { $api } = useNuxtApp();
    const env = await $api<{ result: number; message: string }>(
      '/api/usage/install-statusline',
      { method: 'POST' }
    );
    if (env.result === 0) {
      // eslint-disable-next-line no-alert
      alert('등록 완료. Claude Code 를 한 번 재시작하세요.');
      await fetchOnce();
    } else {
      // eslint-disable-next-line no-alert
      alert(env.message || '설치 실패');
    }
  } catch (e) {
    // eslint-disable-next-line no-alert
    alert(`설치 호출 실패: ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    installing.value = false;
  }
}

const resetText = computed(() => {
  if (!usage.value.fiveHourResetsAt) return '';
  const d = new Date(usage.value.fiveHourResetsAt * 1000);
  return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
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

onMounted(() => {
  void fetchOnce();
  timer = setInterval(fetchOnce, 10_000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.local-usage {
  background: #fff;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
}
.local-usage-head {
  display: flex; align-items: center; justify-content: space-between;
}
.local-usage-title {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; color: #475569;
}
.install-btn {
  height: 28px; padding: 0 12px;
  background: #0062ff; color: #fff;
  border: none; border-radius: 6px;
  font-size: 12px; font-weight: 600; cursor: pointer;
}
.install-btn:hover:not(:disabled) { background: #0052d4; }
.install-btn:disabled { background: #94A3B8; cursor: not-allowed; }
.install-help {
  margin: 8px 0 0; padding: 0;
  font-size: 11px; color: #94A3B8; line-height: 1.5;
}
.install-help code {
  font-size: 11px; padding: 1px 5px; border-radius: 3px;
  background: #F1F5F9; color: #475569;
}

.local-usage-row {
  display: grid; gap: 18px;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}
.metric { display: flex; flex-direction: column; gap: 5px; }
.metric-label {
  font-size: 11px; font-weight: 600; color: #475569;
  display: flex; align-items: center; gap: 6px;
}
.reset-hint { font-weight: 400; color: #94A3B8; }
.metric-bar {
  height: 6px; background: #F1F5F9; border-radius: 4px; overflow: hidden;
}
.metric-fill {
  height: 100%; border-radius: 4px; transition: width .3s;
}
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
