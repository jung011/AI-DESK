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

  // ---------------- 추가 debug layer — *진짜 freeze* 잡기 ----------------

  // 1. Long task observer — main thread 50ms+ block 박은 task (freeze 의 진짜 원인 후보)
  //    PerformanceObserver 의 'longtask' = Web Performance API. 메인 thread 가 50ms+ 점유 시 발사.
  try {
    const longTaskObserver = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        // 100ms 넘는 것만 박음 (50-100ms 는 noise — 정상 render 도 그 정도)
        if (entry.duration >= 100) {
          trace('perf:longtask', {
            duration: Math.round(entry.duration),
            startTime: Math.round(entry.startTime),
            name: entry.name,
          });
        }
      }
    });
    longTaskObserver.observe({ entryTypes: ['longtask'] });
  } catch { /* 일부 브라우저 미지원 */ }

  // 2. fetch wrapper — 모든 HTTP request 의 결과 trace. fail / 4xx / 5xx 잡음.
  //    *page reload 안 trigger 하는 silent error* 잡는 핵심.
  const originalFetch = window.fetch.bind(window);
  window.fetch = async function patchedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = typeof input === 'string' ? input : (input instanceof URL ? input.href : input.url);
    const method = init?.method || 'GET';
    const started = performance.now();
    // logs/client 호출은 self-trace 회피 (infinite loop 차단)
    const isSelfTrace = url.includes('/api/logs/client');
    try {
      const res = await originalFetch(input, init);
      const elapsed = Math.round(performance.now() - started);
      if (!isSelfTrace && (!res.ok || elapsed > 3000)) {
        trace('fetch:result', {
          method,
          url: url.length > 200 ? url.slice(0, 200) + '...' : url,
          status: res.status,
          ok: res.ok,
          elapsedMs: elapsed,
        });
      }
      return res;
    } catch (e) {
      const elapsed = Math.round(performance.now() - started);
      if (!isSelfTrace) {
        trace('fetch:error', {
          method,
          url: url.length > 200 ? url.slice(0, 200) + '...' : url,
          message: String((e as Error)?.message ?? e),
          elapsedMs: elapsed,
        });
      }
      throw e;
    }
  };

  // 3. WebSocket lifecycle — open / close / error 박음. *ws disconnect storm* 진단.
  const OriginalWS = window.WebSocket;
  // Patch via wrapper class — original prototype 유지
  // @ts-expect-error — window.WebSocket 타입 덮어쓰기
  window.WebSocket = function PatchedWS(url: string, protocols?: string | string[]) {
    const ws = new OriginalWS(url, protocols);
    const shortUrl = url.length > 100 ? url.slice(0, 100) + '...' : url;
    trace('ws:new', { url: shortUrl });
    ws.addEventListener('open', () => trace('ws:open', { url: shortUrl }));
    ws.addEventListener('close', (e) => trace('ws:close', { url: shortUrl, code: e.code, reason: e.reason }));
    ws.addEventListener('error', () => trace('ws:error', { url: shortUrl }));
    return ws;
  } as unknown as typeof WebSocket;
  // @ts-expect-error — copy static properties
  Object.assign(window.WebSocket, OriginalWS);

  // 4. Memory snapshot — freeze 직전 의 사용량 보존. Chrome 만 지원.
  try {
    const perf = performance as Performance & { memory?: { usedJSHeapSize: number; totalJSHeapSize: number; jsHeapSizeLimit: number } };
    if (perf.memory) {
      setInterval(() => {
        const m = perf.memory!;
        // heap 의 80% 이상 사용 시만 박음 — noise 줄임
        if (m.usedJSHeapSize / m.jsHeapSizeLimit > 0.8) {
          trace('perf:memory-high', {
            usedMB: Math.round(m.usedJSHeapSize / 1024 / 1024),
            totalMB: Math.round(m.totalJSHeapSize / 1024 / 1024),
            limitMB: Math.round(m.jsHeapSizeLimit / 1024 / 1024),
          });
        }
      }, 10000);
    }
  } catch { /* unsupported */ }

  // 콘솔 helper — 사용자가 history 빠르게 dump 할 수 있게.
  (window as unknown as { aideskDebugTrace?: () => unknown }).aideskDebugTrace = () => {
    try {
      const raw = window.localStorage.getItem(LS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  };

  // 콘솔 helper 2 — *특정 event* 만 filter dump
  (window as unknown as { aideskDebugTraceFilter?: (q: string) => unknown }).aideskDebugTraceFilter = (q: string) => {
    try {
      const raw = window.localStorage.getItem(LS_KEY);
      const list = raw ? JSON.parse(raw) : [];
      return list.filter((e: { event: string }) => e.event.includes(q));
    } catch { return []; }
  };
});
