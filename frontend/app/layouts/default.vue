<template>
  <div class="app-shell">
    <HeaderView />
    <LeftMenuView />
    <main class="app-main" :class="{ 'menu-open': layout.sideMenuOpen }">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useLayoutStore } from '~/stores/layout';
import { useMessagesStore } from '~/stores/messages';
import HeaderView from '~/components/layout/HeaderView.vue';
import LeftMenuView from '~/components/layout/LeftMenuView.vue';

const layout = useLayoutStore();
const messages = useMessagesStore();

// 미확인 메시지 카운트 — 사이드 메뉴/대시보드 카드 뱃지가 모두 구독한다.
let unreadPoll: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  void messages.fetchUnreadCount();
  unreadPoll = setInterval(() => void messages.fetchUnreadCount(), 10_000);
});
onUnmounted(() => {
  if (unreadPoll !== null) clearInterval(unreadPoll);
});
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #F4F6FB;
}
.app-main {
  padding-top: 104px;        /* header-top 56 + header-bottom 48 */
  padding-left: 0;
  transition: padding-left .15s;
  min-height: calc(100vh - 104px);
}
.app-main.menu-open {
  padding-left: 245px;
}
</style>
