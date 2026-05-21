<template>
  <section class="colleague-section">
    <div class="colleague-head">
      <h3 class="colleague-title">사내 동료 AI</h3>
      <span class="colleague-summary">
        <span class="online-dot online" /> 온라인 {{ onlineCount }}
        <span class="colleague-sep">·</span>
        전체 {{ colleagues.list.value.length }}
      </span>
    </div>

    <div class="colleague-hint">
      조회용 패널 — 사내 동료에게 메시지는 외부 터미널의 (me) claude 에서
      <code>mcp__aidesk-channel__send_to</code> 로 보냅니다.
    </div>

    <div v-if="colleagues.list.value.length === 0" class="colleague-empty">
      가입한 사내 동료가 없습니다.
      <small class="colleague-empty-hint">
        새 동료는 <code>POST /api/auth/signup</code> 으로 가입 후 (me) 워크스페이스 지정 시 여기 표시됩니다.
      </small>
    </div>

    <div v-else class="colleague-grid">
      <div
        v-for="c in sorted"
        :key="c.accountSn"
        class="colleague-card"
        :class="{ offline: !c.online, 'me-unset': !c.meAgentId }">
        <span class="online-dot" :class="{ online: c.online }" />
        <div class="colleague-name">
          {{ c.displayName || c.loginId }}
          <span v-if="!c.meAgentId" class="me-unset-tag">(me) 미지정</span>
        </div>
        <div class="colleague-meta">
          {{ c.loginId }}
        </div>
        <div v-if="c.meAgentId" class="colleague-status">
          <span class="status-badge" :class="`status-${c.meStatus}`">{{ c.meStatus }}</span>
          <span v-if="c.meContextPct != null" class="ctx-pct">ctx {{ c.meContextPct }}%</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue';
import { useColleagues } from '~/composables/useColleagues';

const colleagues = useColleagues();
const POLL_INTERVAL_MS = 10_000;
let timer: ReturnType<typeof setInterval> | null = null;

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

.colleague-hint {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #F4F6FB;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}
.colleague-hint code {
  background: #FFFFFF;
  padding: 1px 5px;
  border-radius: 3px;
  border: 1px solid #E2E8F0;
  font-family: monospace;
  font-size: 11px;
  color: #444;
}

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
.colleague-status {
  display: flex; align-items: center; gap: 6px; margin-top: 2px;
}
.status-badge {
  font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 8px;
}
.status-active  { background: #E8F5E9; color: #2E7D32; }
.status-waiting { background: #E3F2FD; color: #0D47A1; }
.status-idle    { background: #FFF8E1; color: #E65100; }
.status-error   { background: #FFEBEE; color: #B71C1C; }
.ctx-pct { font-size: 10px; color: #888; }
</style>
