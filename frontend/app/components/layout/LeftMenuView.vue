<template>
  <nav class="side-menu" :class="{ 'is-closed': !layout.sideMenuOpen }">
    <div class="side-menu-logo">
      <h1>AI 사무실</h1>
    </div>

    <ul class="side-menu-list">
      <li class="side-menu-section-label">모니터링</li>

      <li class="side-menu-item" :class="{ active: route.path.startsWith('/dashboard') || route.path === '/' }">
        <NuxtLink class="side-menu-link" to="/dashboard">
          <svg class="menu-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" />
          </svg>
          대시보드
        </NuxtLink>
      </li>

      <li class="side-menu-item" :class="{ active: route.path.startsWith('/logs') }">
        <NuxtLink class="side-menu-link" to="/logs">
          <svg class="menu-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M13 3a9 9 0 0 1 9 9H13V3zM3 13a9 9 0 0 0 9 9v-9H3zm10 0v9a9 9 0 0 0 9-9h-9z" />
          </svg>
          실행 로그
        </NuxtLink>
      </li>

      <li class="side-menu-divider" />

      <li class="side-menu-section-label">협업</li>
      <li class="side-menu-item" :class="{ active: route.path.startsWith('/messages') }">
        <NuxtLink class="side-menu-link" to="/messages">
          <svg class="menu-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z" />
          </svg>
          메시지
          <span v-if="unreadCount > 0" class="menu-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
        </NuxtLink>
      </li>

      <li class="side-menu-item" :class="{ active: route.path.startsWith('/rooms') }">
        <NuxtLink class="side-menu-link" to="/rooms">
          <svg class="menu-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
          </svg>
          협업방
        </NuxtLink>
      </li>

      <li class="side-menu-divider" />

      <li class="side-menu-section-label">관리</li>
      <li class="side-menu-item" :class="{ active: route.path.startsWith('/settings') }">
        <NuxtLink class="side-menu-link" to="/settings">
          <svg class="menu-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
          </svg>
          설정
        </NuxtLink>
      </li>
    </ul>
  </nav>
</template>

<script setup lang="ts">
import { useLayoutStore } from '~/stores/layout';
import { useMessagesStore } from '~/stores/messages';

const layout = useLayoutStore();
const messages = useMessagesStore();
const route = useRoute();

/** messages store 의 totalUnread 를 구독 — 폴링은 default layout 이 담당. */
const unreadCount = computed(() => messages.unread.totalUnread);
</script>

<style scoped>
.side-menu {
  position: fixed; top: 0; left: 0; bottom: 0;
  width: 245px; background: #1E293B;
  display: flex; flex-direction: column;
  z-index: 200;
  transition: width .15s, opacity .15s;
}
.side-menu.is-closed {
  width: 0;
  overflow: hidden;
}
.side-menu-logo {
  height: 56px; display: flex; align-items: center;
  padding: 0 20px; border-bottom: 1px solid #334155;
  flex-shrink: 0;
}
.side-menu-logo h1 {
  font-size: 13px; font-weight: 600; color: #94A3B8;
  letter-spacing: .06em; text-transform: uppercase;
}

.side-menu-list { flex: 1; overflow-y: auto; padding: 8px 0; list-style: none; margin: 0; }
.side-menu-list::-webkit-scrollbar { width: 4px; }
.side-menu-list::-webkit-scrollbar-thumb { background: #475569; border-radius: 2px; }

.side-menu-section-label {
  padding: 10px 20px 4px;
  font-size: 11px; font-weight: 600; color: #475569;
  letter-spacing: .08em; text-transform: uppercase;
  list-style: none;
}
.side-menu-link {
  display: flex; align-items: center; gap: 10px;
  height: 42px; padding: 0 20px;
  font-size: 14px; color: #94A3B8;
  text-decoration: none; cursor: pointer;
  transition: background .15s, color .15s;
}
.side-menu-link .menu-icon { width: 17px; height: 17px; flex-shrink: 0; opacity: .7; }
.side-menu-link:hover { background: #334155; color: #E2E8F0; }
.side-menu-link:hover .menu-icon { opacity: 1; }
.side-menu-item.active .side-menu-link {
  background: #0062ff; color: #fff; font-weight: 600;
}
.side-menu-item.active .side-menu-link .menu-icon { opacity: 1; }
.side-menu-divider {
  height: 1px; background: #334155; margin: 6px 16px;
  list-style: none;
}

.menu-badge {
  margin-left: auto;
  min-width: 20px; height: 18px; padding: 0 6px;
  border-radius: 9px; background: #E53935; color: #fff;
  font-size: 10px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
}
</style>
