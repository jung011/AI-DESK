import { defineStore } from 'pinia';

interface LayoutState {
  sideMenuOpen: boolean;
}

/**
 * UI 레이아웃 상태 — 사이드메뉴 open/close.
 * 사용자 식별 정보는 ~/stores/auth.ts 의 useAuthStore() 사용.
 */
export const useLayoutStore = defineStore('layout', {
  state: (): LayoutState => ({
    // 시작 시 닫힘 — 사용자가 햄버거를 눌러 연다.
    sideMenuOpen: false,
  }),
  actions: {
    toggleSideMenu() {
      this.sideMenuOpen = !this.sideMenuOpen;
    },
  },
});
