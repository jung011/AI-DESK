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
      <button
        v-for="a in sorted"
        :key="a.employeeId"
        type="button"
        class="external-card"
        :class="{ offline: !a.online }"
        @click="openDetail(a)">
        <span class="online-dot" :class="{ online: a.online }" />
        <div class="external-name">{{ a.name || a.employeeId }}</div>
        <div class="external-dept">{{ a.department || '—' }}</div>
      </button>
    </div>

    <Teleport to="body">
      <div v-if="selected" class="popup-overlay" @click.self="selected = null">
        <div class="popup-box" role="dialog">
          <header class="popup-head">
            <div class="popup-title-wrap">
              <span class="online-dot" :class="{ online: selected.online }" />
              <h3>{{ selected.name || selected.employeeId }}</h3>
            </div>
            <button class="popup-close" type="button" @click="selected = null">×</button>
          </header>
          <div class="popup-body">
            <div class="meta-row">
              <span class="meta-label">부서</span>
              <span class="meta-value">{{ selected.department || '—' }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">상태</span>
              <span class="meta-value">{{ selected.online ? '온라인' : '오프라인' }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">ID</span>
              <span class="meta-value mono">{{ selected.employeeId }}</span>
            </div>
            <div class="skills-section">
              <div class="skills-title">스킬 ({{ selected.skills.length }})</div>
              <div v-if="selected.skills.length === 0" class="skills-empty">등록된 스킬 없음</div>
              <div v-else class="skills-list">
                <span v-for="s in selected.skills" :key="s" class="skill-chip">{{ s }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type { ExternalAgentItem } from '~/vo/external/ExternalAgentVo';

const list = ref<ExternalAgentItem[]>([]);
const selected = ref<ExternalAgentItem | null>(null);

function openDetail(a: ExternalAgentItem): void {
  selected.value = a;
}

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
  font: inherit; color: inherit; text-align: left;
  cursor: pointer;
  transition: border-color .15s, background .15s, transform .08s;
}
.external-card.offline { background: #FAFBFD; }
.external-card:hover { border-color: #0062ff; background: #F8FAFC; }
.external-card:active { transform: scale(.98); }

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

/* === 스킬 모달 === */
.popup-overlay {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100;
}
.popup-box {
  width: 440px; max-width: calc(100vw - 40px); max-height: calc(100vh - 80px);
  background: #fff; border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
  display: flex; flex-direction: column;
}
.popup-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #F0F2F5;
}
.popup-title-wrap { display: inline-flex; align-items: center; gap: 8px; }
.popup-head h3 { margin: 0; font-size: 15px; font-weight: 700; color: #101010; }
.popup-close {
  width: 28px; height: 28px;
  background: none; border: none; font-size: 22px;
  color: #94A3B8; cursor: pointer; line-height: 1;
}
.popup-close:hover { color: #475569; }
.popup-body { padding: 18px 20px; overflow-y: auto; }

.meta-row {
  display: flex; gap: 12px; padding: 5px 0;
  font-size: 13px;
}
.meta-label {
  flex-shrink: 0; width: 60px;
  color: #94A3B8; font-weight: 600;
}
.meta-value { color: #1E293B; }
.meta-value.mono { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; }

.skills-section {
  margin-top: 14px; padding-top: 14px;
  border-top: 1px solid #F0F2F5;
}
.skills-title {
  font-size: 12px; font-weight: 700; color: #475569;
  margin-bottom: 8px;
}
.skills-empty { font-size: 12px; color: #94A3B8; }
.skills-list { display: flex; flex-wrap: wrap; gap: 6px; }
.skill-chip {
  display: inline-flex; align-items: center;
  padding: 4px 10px; border-radius: 12px;
  background: #EEF2FF; color: #4338CA;
  font-size: 11px; font-weight: 600;
}
</style>
