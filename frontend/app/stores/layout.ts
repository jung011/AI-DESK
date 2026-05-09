import { defineStore } from 'pinia';

interface LayoutState {
  sideMenuOpen: boolean;
  user: { name: string };
}

export const useLayoutStore = defineStore('layout', {
  state: (): LayoutState => ({
    sideMenuOpen: true,
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
