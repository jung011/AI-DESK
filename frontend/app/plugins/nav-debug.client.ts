/**
 * navigation / lifecycle 트레이서 — *throw 없이도* 페이지 사라짐 진단 위한 광범위 로그.
 *
 * error-tracker.client.ts 는 Vue/window error / unhandledrejection 만 잡음.
 * 페이지가 *조용히* 사라지는 path (router redirect / pagehide / SW reload / JWT refresh /
 * beforeunload) 는 error 가 아니라 일반 event → 별도 추적 필요.
 *
 * 적재 path 2:
 *   - clientLog('log', ...) → backend app.client 채널 (K8s stdout)
 *   - localStorage (`aidesk.debug.nav-trace`) → 새로고침 / SW reload 후에도 보존,
 *     사용자가 console 에 `localStorage.getItem('aidesk.debug.nav-trace')` 박으면 history 확보
 */
import { clientLog } from '~/utils/clientLogger';

const LS_KEY = 'aidesk.debug.nav-trace';
const LS_MAX = 200;

function persist(event: string, detail?: unknown): void {
  if (typeof window === 'undefined') return;
  try {
    const stamp = new Date().toISOString();
    const entry = { t: stamp, event, route: window.location.pathname + window.location.search, detail };
    const raw = window.localStorage.getItem(LS_KEY);
    let list: unknown[] = [];
    try { list = raw ? JSON.parse(raw) : []; } catch { list = []; }
    if (!Array.isArray(list)) list = [];
    list.push(entry);
    if (list.length > LS_MAX) list = list.slice(-LS_MAX);
    window.localStorage.setItem(LS_KEY, JSON.stringify(list));
  } catch { /* quota / SecurityError 무시 */ }
}

function trace(event: string, detail?: unknown): void {
  persist(event, detail);
  // backend 도 적재 (best-effort). clientLog 는 keepalive: true 라 navigation 도중도 살림.
  clientLog('log', `nav-debug:${event}`, detail);
}

export default defineNuxtPlugin((nuxtApp) => {
  if (typeof window === 'undefined') return;

  // router transitions
  const router = useRouter();
  router.beforeEach((to, from) => {
    trace('router:beforeEach', { from: from.fullPath, to: to.fullPath });
  });
  router.afterEach((to, from) => {
    trace('router:afterEach', { from: from.fullPath, to: to.fullPath });
  });
  router.onError((err, to, from) => {
    trace('router:onError', { from: from?.fullPath, to: to?.fullPath, message: String(err?.message ?? err) });
  });

  // page lifecycle
  window.addEventListener('beforeunload', () => {
    trace('window:beforeunload');
  });
  window.addEventListener('pagehide', (e) => {
    trace('window:pagehide', { persisted: (e as PageTransitionEvent).persisted });
  });
  window.addEventListener('pageshow', (e) => {
    trace('window:pageshow', { persisted: (e as PageTransitionEvent).persisted });
  });
  document.addEventListener('visibilitychange', () => {
    trace('document:visibilitychange', { state: document.visibilityState });
  });

  // 연결 상태
  window.addEventListener('online', () => trace('window:online'));
  window.addEventListener('offline', () => trace('window:offline'));

  // Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      trace('sw:controllerchange');
    });
    navigator.serviceWorker.addEventListener('message', (e) => {
      trace('sw:message', { type: (e.data as { type?: string })?.type });
    });
  }

  // 초기 mount 시 한 번
  trace('plugin:init', {
    ua: navigator.userAgent.slice(0, 200),
    online: navigator.onLine,
    visibility: document.visibilityState,
  });

  // 콘솔 helper — 사용자가 history 빠르게 dump 할 수 있게.
  (window as unknown as { aideskDebugTrace?: () => unknown }).aideskDebugTrace = () => {
    try {
      const raw = window.localStorage.getItem(LS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  };
});
