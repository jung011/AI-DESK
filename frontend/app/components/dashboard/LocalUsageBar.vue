<template>
  <div class="local-usage" :title="usage.source || '활성 Claude 세션 없음'">
    <div class="local-usage-head">
      <div class="local-usage-title">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/>
        </svg>
        <span>로컬 Claude 통합 사용량</span>
      </div>
      <div class="local-usage-pct" :class="level">
        {{ usage.pct }}%
        <span class="local-usage-tokens">({{ formatTokens(usage.tokens) }} / {{ formatTokens(usage.window) }})</span>
      </div>
    </div>
    <div class="local-usage-bar">
      <div class="local-usage-fill" :class="level" :style="{ width: usage.pct + '%' }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface LocalUsage {
  pct: number;
  tokens: number;
  window: number;
  source: string;
}

const usage = ref<LocalUsage>({ pct: 0, tokens: 0, window: 1_000_000, source: '' });

const level = computed(() => {
  const v = usage.value.pct;
  if (v >= 90) return 'high';
  if (v >= 70) return 'mid';
  return 'low';
});

let timer: ReturnType<typeof setInterval> | null = null;

async function fetchOnce(): Promise<void> {
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<LocalUsage>>('/api/usage/local');
    if (env.result === 0 && env.data) usage.value = env.data;
  } catch {
    // 폴링이라 무시 — 다음 틱에서 재시도
  }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return Math.round(n / 1_000) + 'k';
  return String(n);
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
  padding: 12px 16px;
  margin-bottom: 16px;
}
.local-usage-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.local-usage-title {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; color: #475569;
}
.local-usage-pct {
  font-size: 13px; font-weight: 700;
}
.local-usage-pct.low { color: #2E7D32; }
.local-usage-pct.mid { color: #E65100; }
.local-usage-pct.high { color: #E53935; }
.local-usage-tokens {
  margin-left: 6px; font-weight: 500; color: #94A3B8;
}
.local-usage-bar {
  height: 6px; background: #F1F5F9; border-radius: 4px; overflow: hidden;
}
.local-usage-fill {
  height: 100%; border-radius: 4px; transition: width .3s;
  background: #00C853;
}
.local-usage-fill.mid { background: #FFB300; }
.local-usage-fill.high { background: #E53935; }
</style>
