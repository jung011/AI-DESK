<template>
  <div class="page_content">
    <h2 style="margin: 0 0 8px;">대시보드</h2>
    <p style="color:#94A3B8;font-size:13px;margin:0 0 24px;">
      Claude Code AI 에이전트 현황을 모니터링합니다 — 화면은 Phase 2에서 구현됩니다.
    </p>

    <!-- 임시 디버그용 — 백엔드 연결 검증 -->
    <pre v-if="error" style="color:#E53935">{{ error }}</pre>
    <pre v-else-if="data">{{ JSON.stringify(data, null, 2) }}</pre>
    <p v-else>로딩…</p>
  </div>
</template>

<script setup lang="ts">
const { $api } = useNuxtApp();
const data = ref<unknown>(null);
const error = ref<string | null>(null);

try {
  data.value = await $api('/api/agents');
} catch (e) {
  error.value = e instanceof Error ? e.message : String(e);
}
</script>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}
</style>
