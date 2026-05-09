<template>
  <div class="page-placeholder">
    <p>대시보드로 이동 중…</p>
  </div>
</template>

<script setup lang="ts">
// 진입 시 즉시 /dashboard 로 보낸다.
await navigateTo('/dashboard');
</script>

<style scoped>
.page-placeholder {
  padding: 28px;
  font-size: 13px;
  color: #94A3B8;
}
</style>
