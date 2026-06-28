<template>
  <div class="summary-row">
    <div class="summary-card">
      <div class="summary-icon total">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="#3B5BDB"><path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z"/></svg>
      </div>
      <div class="summary-info">
        <span class="summary-label">전체 AI</span>
        <span class="summary-count">{{ summary.total }}</span>
      </div>
    </div>

    <div class="summary-card">
      <div class="summary-icon working">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="#2E7D32"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg>
      </div>
      <div class="summary-info">
        <span class="summary-label">작업중</span>
        <span class="summary-count">{{ summary.active }}</span>
      </div>
    </div>

    <div class="summary-card">
      <div class="summary-icon waiting">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="#0D47A1"><path d="M12 2a10 10 0 100 20 10 10 0 000-20zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26A2 2 0 1010 9H8a4 4 0 118 0c0 .88-.36 1.68-.93 2.25z"/></svg>
      </div>
      <div class="summary-info">
        <span class="summary-label">응답 대기</span>
        <span class="summary-count">{{ summary.waiting ?? 0 }}</span>
      </div>
    </div>

    <div class="summary-card">
      <div class="summary-icon idle">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="#E65100"><path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z"/></svg>
      </div>
      <div class="summary-info">
        <span class="summary-label">대기중</span>
        <span class="summary-count">{{ summary.idle }}</span>
      </div>
    </div>

    <div class="summary-card">
      <div class="summary-icon error">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="#B71C1C"><path d="M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
      </div>
      <div class="summary-info">
        <span class="summary-label">오류</span>
        <span class="summary-count">{{ summary.error ?? 0 }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgentSummary } from '~/vo/agents/AgentVo';

defineProps<{ summary: AgentSummary }>();
</script>

<style scoped>
.summary-row { display: flex; gap: 16px; margin-bottom: 20px; }
.summary-card {
  flex: 1; background: var(--bg-card); border: 1px solid #D4DCE4;
  border-radius: 6px; padding: 16px 20px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .12);
  display: flex; align-items: center; gap: 14px;
}
.summary-icon {
  width: 42px; height: 42px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.summary-icon.total   { background: #EEF2FF; }
.summary-icon.working { background: #E8F5E9; }
.summary-icon.waiting { background: #E3F2FD; }
.summary-icon.idle    { background: #FFF8E1; }
.summary-icon.error   { background: #FFEBEE; }
.summary-info { display: flex; flex-direction: column; gap: 2px; }
.summary-label { font-size: 12px; color: #999; font-weight: 500; }
.summary-count {
  font-size: 26px; font-weight: 700; color: #101010;
  line-height: 1.2; letter-spacing: -.04em;
}
</style>
