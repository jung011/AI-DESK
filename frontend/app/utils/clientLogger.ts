/**
 * client-side 진단 logger — console + backend 적재 동시.
 *
 * 호출 시 console.{level} + `POST /api/logs/client` (best-effort, fail 시 silent).
 * backend 는 `app.client` 채널의 application log 에 박음 (K8s stdout 에 모임).
 *
 * **순환 호출 차단** — backend POST 는 *native fetch* 로 진행 ($api wrapper 우회).
 * $api 의 401 interceptor 가 client log 를 발사하는 path 에서 무한 루프 방지.
 *
 * 사용 — 사고 분기 (logout / 401 / refresh fail / unexpected exception) 에서만 호출.
 * 평시 noise 최소화 — info / debug 호출 X.
 */

type Level = 'log' | 'warn' | 'error';

export function clientLog(level: Level, msg: string, data?: unknown): void {
  // console — 즉시 visible
  try {
    if (typeof console !== 'undefined' && typeof console[level] === 'function') {
      console[level](`[client-log] ${msg}`, data ?? '');
    }
  } catch { /* ignore */ }

  // backend 적재 — best-effort
  if (typeof window === 'undefined') return;
  try {
    const baseURL = (window as unknown as { __NUXT__?: { config?: { public?: { apiBase?: string } } } })
      .__NUXT__?.config?.public?.apiBase || window.location.origin;
    const route = window.location.pathname + window.location.search;
    // sanitize data — Error 객체 → message + stack
    let serialized: unknown = data;
    if (data instanceof Error) {
      serialized = { message: data.message, stack: data.stack };
    }
    void fetch(`${baseURL}/api/logs/client`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, msg, data: serialized, route }),
      keepalive: true, // navigation 도중 호출 시 request 살리기 (logout redirect path 안전)
    }).catch(() => { /* silent — log 적재 fail 이 user impact 만들면 안 됨 */ });
  } catch { /* ignore */ }
}
