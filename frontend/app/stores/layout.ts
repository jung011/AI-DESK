import { defineStore } from 'pinia';

interface LayoutState {
  sideMenuOpen: boolean;
  user: { name: string };
}

export const useLayoutStore = defineStore('layout', {
  state: (): LayoutState => ({
    // 시작 시 닫힘 — 사용자가 햄버거를 눌러 열도록 (sample 패턴과 동일)
    sideMenuOpen: false,
    user: { name: 'admin' }
  }),
  actions: {
    toggleSideMenu() {
      this.sideMenuOpen = !this.sideMenuOpen;
    },
    setUser(name: string) {
      this.user.name = name;
    }
  }
});
