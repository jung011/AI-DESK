/**
 * 글로벌 error tracker — Vue / window 의 *unhandled* 사고 자동 backend 적재.
 *
 * 옛엔 `clientLog()` 가 *명시 호출 path* 에서만 박혀 (logout / 401 / refresh fail).
 * Vue 컴포넌트 안 unhandled error + script error + Promise rejection 은 *console only*
 * → 재발 시 사고 진단 어려움.
 *
 * 이 plugin 이 3 listener 박아 *모든 unhandled* → POST /api/logs/client (`app.client` 채널).
 * - app.config.errorHandler  — Vue 컴포넌트 안 error
 * - window.onerror           — script load / runtime error
 * - window.onunhandledrejection — Promise rejection
 *
 * .client.ts suffix = SSR skip (server side 의 process.on path 와 분리).
 */
import { clientLog } from '~/utils/clientLogger';

export default defineNuxtPlugin((nuxtApp) => {
  // 1) Vue 컴포넌트 안 error
  nuxtApp.vueApp.config.errorHandler = (err, instance, info) => {
    const msg = err instanceof Error ? err.message : String(err);
    const stack = err instanceof Error ? err.stack : undefined;
    const componentName = instance?.$options?.name || instance?.$options?.__name || 'unknown';
    clientLog('error', `vue:errorHandler ${componentName} (${info}): ${msg}`, { stack });
  };

  // 2) script / runtime error
  if (typeof window !== 'undefined') {
    window.addEventListener('error', (event) => {
      const msg = event.message || String(event.error);
      const file = event.filename ? `${event.filename}:${event.lineno}` : 'unknown';
      const stack = event.error instanceof Error ? event.error.stack : undefined;
      clientLog('error', `window:error ${file} — ${msg}`, { stack });
    });

    // 3) Promise rejection (await + throw 또는 .then 없는 catch)
    window.addEventListener('unhandledrejection', (event) => {
      const reason = event.reason;
      const msg = reason instanceof Error ? reason.message : String(reason);
      const stack = reason instanceof Error ? reason.stack : undefined;
      clientLog('error', `window:unhandledrejection — ${msg}`, { stack });
    });
  }
});
