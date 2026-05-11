<template>
  <section class="external-section">
    <div class="external-head">
      <h3 class="external-title">사내 동료 AI</h3>
      <span class="external-summary">
        <span class="online-dot online" /> 온라인 {{ onlineCount }}
        <span class="external-sep">·</span>
        전체 {{ list.length }}
      </span>
    </div>

    <div v-if="list.length === 0" class="external-empty">
      등록된 외부 에이전트가 없습니다.
    </div>

    <div v-else class="external-grid">
      <div
        v-for="a in sorted"
        :key="a.employeeId"
        class="external-card"
        :class="{ offline: !a.online }">
        <span class="online-dot" :class="{ online: a.online }" />
        <div class="external-name">{{ a.name || a.employeeId }}</div>
        <div class="external-dept">{{ a.department || '—' }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type { ExternalAgentItem } from '~/vo/external/ExternalAgentVo';

const list = ref<ExternalAgentItem[]>([]);

const onlineCount = computed(() => list.value.filter((a) => a.online).length);

/** 온라인 우선 + 이름 오름차순 */
const sorted = computed(() => {
  return [...list.value].sort((a, b) => {
    if (a.online !== b.online) return a.online ? -1 : 1;
    return (a.name || a.employeeId).localeCompare(b.name || b.employeeId);
  });
});

let timer: ReturnType<typeof setInterval> | null = null;

async function fetchOnce(): Promise<void> {
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<ExternalAgentItem[]>>('/api/external-agents');
    if (env.result === 0 && Array.isArray(env.data)) list.value = env.data;
  } catch {
    /* swallow — 다음 폴링에서 재시도 */
  }
}

onMounted(() => {
  void fetchOnce();
  timer = setInterval(fetchOnce, 30_000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.external-section {
  margin-top: 24px;
  background: #fff;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 16px 18px;
}
.external-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 12px;
}
.external-title {
  margin: 0; font-size: 14px; font-weight: 700; color: #101010;
}
.external-summary {
  font-size: 12px; color: #475569;
  display: inline-flex; align-items: center; gap: 6px;
}
.external-sep { color: #CBD5E1; }

.external-empty {
  padding: 24px 0; text-align: center;
  color: #94A3B8; font-size: 13px;
}

.external-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.external-card {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border: 1px solid #E2E8F0; border-radius: 6px;
  background: #fff;
  transition: border-color .15s;
}
.external-card.offline { background: #FAFBFD; }
.external-card:hover { border-color: #CBD5E1; }

.online-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #CBD5E1;
  flex-shrink: 0;
}
.online-dot.online { background: #00C853; }

.external-name {
  font-size: 13px; font-weight: 600; color: #1E293B;
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.external-dept {
  font-size: 11px; color: #94A3B8;
  flex-shrink: 0;
}
</style>
