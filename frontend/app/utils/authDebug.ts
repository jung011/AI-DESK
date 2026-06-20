/**
 * auth 디버깅 logger — console + localStorage 동시 기록.
 *
 * 사고 시점에 navigation (router.replace → /login) 으로 console message 가
 * clear 되어 진단 불가했음. localStorage 는 navigation 후에도 persist 되어
 * 사용자 mac 의 devtools application > storage > localStorage 에서 직접 확인 가능.
 *
 * Application 진단 (sessionStorage, cookie, navigation 패턴) 추적용. 평시
 * 로그도 같이 남도록 모든 auth path 의 진입/통과 시점에 호출.
 */

const STORAGE_KEY = 'aidesk.debugLog';
const MAX_ENTRIES = 200;

type Level = 'log' | 'warn' | 'error';

export function authDebug(level: Level, msg: string, data?: unknown): void {
  const entry = { level, msg, data, time: new Date().toISOString() };
  try {
    // 콘솔에도 박음 (preserve log ON 인 사용자용)
    if (typeof console !== 'undefined' && typeof console[level] === 'function') {
      console[level](`[auth-debug] ${msg}`, data ?? '');
    }
  } catch {
    /* ignore */
  }
  try {
    if (typeof window === 'undefined') return;
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const arr: unknown[] = raw ? JSON.parse(raw) : [];
    if (Array.isArray(arr)) {
      arr.push(entry);
      while (arr.length > MAX_ENTRIES) arr.shift();
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(arr));
    }
  } catch {
    /* localStorage quota / parse error — 무시 */
  }
}

/** devtools console 에서 `window.__aideskDebugLog()` 로 한 줄에 dump. */
if (typeof window !== 'undefined') {
  (window as unknown as { __aideskDebugLog?: () => unknown }).__aideskDebugLog = () => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return null;
    }
  };
}
