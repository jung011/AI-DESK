<template>
  <div class="page-placeholder">
    <p>대시보드로 이동 중…</p>
  </div>
</template>

<script setup lang="ts">
// root 진입 시 /dashboard 로 보낸다.
// `await navigateTo` (top-level await) 패턴은 Vue Suspense 가 컴포넌트 mount 를 block 하여
// 외부 link (예: 메타버스 → 대시보드) 진입 시 하얀 화면 → 새로고침 회피 사고로 이어진다.
// `definePageMeta.redirect` 는 라우터가 mount 전에 redirect 를 처리하므로 mount 자체가 발생 X.
definePageMeta({
  redirect: '/dashboard',
});
</script>

<style scoped>
.page-placeholder {
  padding: 28px;
  font-size: 13px;
  color: #94A3B8;
}
</style>
