<template>
  <section class="colleague-section">
    <div class="colleague-head">
      <h3 class="colleague-title">사내 동료 AI</h3>
      <div class="colleague-head-right">
        <span class="colleague-summary">
          <span class="online-dot online" /> 온라인 {{ onlineCount }}
          <span class="colleague-sep">·</span>
          전체 {{ colleagues.list.value.length }}
        </span>
        <button class="ext-add-btn" @click="dialogOpen = true">+ 외부 AI</button>
      </div>
    </div>

    <ExternalAgentDialog v-model="dialogOpen" @created="onExternalCreated" />

    <div v-if="colleagues.list.value.length === 0" class="colleague-empty">
      가입한 사내 동료가 없습니다.
      <small class="colleague-empty-hint">
        새 동료는 <code>POST /api/auth/signup</code> 으로 가입 후 (me) 워크스페이스 지정 시 여기 표시됩니다.
      </small>
    </div>

    <div v-else class="colleague-grid">
      <div
        v-for="c in sorted"
        :key="c.meAgentId ?? `acc-${c.accountSn}`"
        class="colleague-card"
        :class="{
          offline: !c.online,
          'me-unset': !c.meAgentId,
          'external': c.agentType === 'external',
        }">
        <span class="online-dot" :class="{ online: c.online }" />
        <div class="colleague-name">
          <template v-if="c.agentType === 'external'">
            {{ c.meAgentName }}
            <span class="external-tag">외부 AI</span>
          </template>
          <template v-else>
            {{ c.displayName || c.loginId }}
            <span v-if="!c.meAgentId" class="me-unset-tag">(me) 미지정</span>
          </template>
        </div>
        <div class="colleague-meta">
          <template v-if="c.agentType === 'external'">
            {{ c.loginId }} · {{ c.meStatus || 'offline' }}
          </template>
          <template v-else>
            {{ c.loginId }}
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useColleagues } from '~/composables/useColleagues';
import ExternalAgentDialog from './ExternalAgentDialog.vue';

const colleagues = useColleagues();
const POLL_INTERVAL_MS = 10_000;
let timer: ReturnType<typeof setInterval> | null = null;

const dialogOpen = ref(false);
function onExternalCreated() {
  colleagues.refresh();
}

onMounted(() => {
  colleagues.refresh();
  timer = setInterval(() => colleagues.refresh(), POLL_INTERVAL_MS);
});

onBeforeUnmount(() => {
  if (timer != null) clearInterval(timer);
});

const sorted = computed(() => {
  return [...colleagues.list.value].sort((a, b) => {
    // online → me 지정 → loginId
    if (a.online !== b.online) return a.online ? -1 : 1;
    if (!!a.meAgentId !== !!b.meAgentId) return a.meAgentId ? -1 : 1;
    return a.loginId.localeCompare(b.loginId);
  });
});

const onlineCount = computed(() =>
  colleagues.list.value.filter((c) => c.online).length,
);
</script>

<style scoped>
.colleague-section {
  margin-top: 24px;
  background: #fff;
  border: 1px solid #D4DCE4;
  border-radius: 8px;
  padding: 18px 20px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .08);
}
.colleague-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.colleague-title { font-size: 15px; font-weight: 700; color: #101010; }
.colleague-head-right {
  display: flex; align-items: center; gap: 12px;
}
.ext-add-btn {
  font-size: 11px; padding: 4px 10px;
  background: #fff; border: 1px solid #D4DCE4; border-radius: 4px;
  color: #2D7FF9; font-weight: 600; cursor: pointer;
}
.ext-add-btn:hover { background: #F2F8FE; border-color: #B6D7F9; }
.colleague-summary {
  font-size: 12px; color: #666;
  display: inline-flex; align-items: center; gap: 6px;
}
.colleague-sep { color: #CBD5E1; }
.online-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #CBD5E1;
  display: inline-block;
}
.online-dot.online { background: #00d084; }

.colleague-empty {
  padding: 32px 20px; text-align: center;
  color: #999; font-size: 13px;
}
.colleague-empty-hint {
  display: block; margin-top: 8px; color: #BBB; font-size: 11px;
}
.colleague-empty-hint code {
  background: #F4F6FB; padding: 1px 4px; border-radius: 3px; font-family: monospace;
}

.colleague-grid {
  display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}
.colleague-card {
  position: relative;
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
  padding: 12px 14px;
  text-align: left;
  font-family: inherit;
  display: flex; flex-direction: column; gap: 4px;
}
.colleague-card.offline { background: #F8FAFC; }
.colleague-card.me-unset { opacity: 0.7; }
.colleague-card .online-dot {
  position: absolute; top: 12px; right: 12px;
}
.colleague-name {
  font-size: 13px; font-weight: 600; color: #222;
  padding-right: 16px;     /* online-dot 공간 */
}
.me-unset-tag {
  font-size: 10px; font-weight: 500; color: #AAB4BE;
  margin-left: 4px;
}
.colleague-meta {
  font-size: 11px; color: #888;
}

/* 외부 AI 카드 — service 형태라 다른 색상 / 배지로 구분. */
.colleague-card.external {
  border-color: #B6D7F9;
  background: #F2F8FE;
}
.colleague-card.external.offline {
  background: #F4F8FC;
}
.external-tag {
  font-size: 10px; font-weight: 600; color: #1F6FCE;
  background: #DEEDFD; padding: 1px 6px; border-radius: 3px;
  margin-left: 6px;
}
</style>
