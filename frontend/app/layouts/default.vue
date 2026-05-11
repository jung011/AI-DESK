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
import HeaderView from '~/components/layout/HeaderView.vue';
import LeftMenuView from '~/components/layout/LeftMenuView.vue';

const layout = useLayoutStore();
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #F4F6FB;
}
.app-main {
  padding-top: 104px;        /* header-top 56 + header-bottom 48 */
  padding-left: 0;
  transition: padding-left 0.25s ease;
  min-height: calc(100vh - 104px);
}
.app-main.menu-open {
  padding-left: 245px;
}
</style>
