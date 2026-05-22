<template>
  <!-- 상단 — 로고 + 서비스명 + 시스템 상태 배지 -->
  <div class="header-top" :style="{ left: layout.sideMenuOpen ? '245px' : '0' }">
    <div class="header-top-left">
      <div class="header-logo-box">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="3" fill="#fff" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12"
                stroke="#fff" stroke-width="2" stroke-linecap="round" />
        </svg>
      </div>
      <span class="header-title">AI 사무실</span>
    </div>
    <div class="header-top-right">
      <a
        v-if="metaverseUrl"
        :href="metaverseUrl"
        class="header-metaverse"
        target="_self"
        rel="noopener">
        🌐 METAVERSE
      </a>
      <div class="header-status-badge">
        <span class="dot"></span>
        <span>시스템 운영중</span>
      </div>
    </div>
  </div>

  <!-- 하단 — 햄버거 + 사용자 + 로그아웃 -->
  <div class="header-bottom" :style="{ left: layout.sideMenuOpen ? '245px' : '0' }">
    <div class="header-bottom-left">
      <button type="button" class="header-burger" @click="layout.toggleSideMenu()" />
    </div>
    <div class="header-bottom-right">
      <span class="header-user" :title="auth.loginId">{{ auth.displayName || '게스트' }}</span>
      <button
        type="button"
        class="header-logout"
        :disabled="signingOut"
        @click="onLogout">
        {{ signingOut ? '로그아웃 중…' : '로그아웃' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useLayoutStore } from '~/stores/layout';
import { useAuthStore } from '~/stores/auth';
import { useAuth } from '~/composables/useAuth';

const layout = useLayoutStore();
const auth = useAuthStore();
const { signOut } = useAuth();
const router = useRouter();

// 메타버스 3D 사무실 진입 링크. NUXT_PUBLIC_METAVERSE_URL 미설정 시 버튼 hide.
const runtime = useRuntimeConfig();
const metaverseUrl = (runtime.public.metaverseUrl as string | undefined) || '';

const signingOut = ref(false);

async function onLogout() {
  if (signingOut.value) return;
  signingOut.value = true;
  try {
    await signOut();
  } finally {
    signingOut.value = false;
    await router.replace('/login');
  }
}
</script>

<style scoped>
.header-top {
  position: fixed; top: 0; left: 0; right: 0;
  height: 56px; background: #f0f2f8; border-bottom: 1px solid #dde1ea;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; z-index: 100;
  transition: left 0.25s ease;
}
.header-top-left { display: flex; align-items: center; gap: 12px; }
.header-logo-box {
  width: 32px; height: 32px; border-radius: 8px;
  background: #0062ff; display: flex; align-items: center; justify-content: center;
}
.header-title { font-size: 15px; font-weight: 600; color: #333; }
.header-top-right { display: flex; align-items: center; gap: 10px; }
.header-metaverse {
  display: inline-flex; align-items: center;
  padding: 4px 10px; border-radius: 20px;
  background: rgba(59, 91, 219, .08); border: 1px solid rgba(59, 91, 219, .25);
  color: #3B5BDB; font-size: 12px; font-weight: 600;
  text-decoration: none;
}
.header-metaverse:hover { background: rgba(59, 91, 219, .15); }
.header-status-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 20px;
  background: rgba(0, 98, 255, .08); border: 1px solid rgba(0, 98, 255, .2);
}
.header-status-badge .dot {
  width: 6px; height: 6px; border-radius: 50%; background: #00d084;
}
.header-status-badge span { font-size: 12px; font-weight: 600; color: #0062ff; }

.header-bottom {
  position: fixed; top: 56px; left: 0; right: 0;
  height: 48px; background: #fff; border-bottom: 1px solid #dde1ea;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; z-index: 99;
  transition: left 0.25s ease;
}
.header-bottom-left { display: flex; align-items: center; }
.header-bottom-right { display: flex; align-items: center; gap: 12px; }

.header-burger {
  width: 32px; height: 32px; cursor: pointer; border: none; padding: 0;
  border-radius: 6px; background: none;
  display: flex; align-items: center; justify-content: center;
}
.header-burger::before {
  content: '';
  display: block; width: 18px; height: 14px;
  background: linear-gradient(
    to bottom,
    #333 0, #333 2px, transparent 2px, transparent 6px,
    #333 6px, #333 8px, transparent 8px, transparent 12px,
    #333 12px, #333 14px
  );
}
.header-burger:hover { background: #F1F5F9; }

.header-user {
  font-size: 13px; font-weight: 600; color: #333;
  display: flex; align-items: center; gap: 6px;
}
.header-user::before {
  content: '';
  display: inline-block; width: 24px; height: 24px;
  border-radius: 50%; background: #E2E8F0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2394A3B8'%3E%3Cpath d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: center; background-size: 16px;
  flex-shrink: 0;
}
.header-logout {
  height: 28px; padding: 0 12px;
  border: 1px solid #D4DCE4; background: #fff;
  border-radius: 6px; font-size: 12px; font-weight: 500; color: #666; cursor: pointer;
}
.header-logout:hover { background: #F8FAFC; border-color: #CBD5E1; }
</style>
