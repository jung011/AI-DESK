import { defineNuxtPlugin } from '#app';
import { useAuthStore } from '~/stores/auth';

/**
 * 클라이언트 부팅 시 sessionStorage 에서 user 복원.
 * 미들웨어가 isAuthenticated 를 보기 전에 hydrate 가 끝나야 한다.
 */
export default defineNuxtPlugin(() => {
  const auth = useAuthStore();
  auth.hydrate();
});
