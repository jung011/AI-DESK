/**
 * 옵션 B MVP — 모바일 frontend 가 *같은 wifi 안* 사용자 mac 의 helper 한테 직접 접근
 * 박을 때 사용. backend `/api/helper/lan-ip` 에서 user 의 helper LAN IP 박힌 거 fetch.
 *
 * 사용 방식:
 *   const base = await getMobileHelperBase();  // "172.20.1.35" or null
 *   const url = base ? `ws://${base}:30084/ws/terminal` : null;
 *
 * 모바일 박혀있을 때만 호출. Desktop = 옛 분기 (`127.0.0.1:30083`) 그대로.
 * fetch 결과 캐시 — 30s TTL (helper 가 30s cycle 마다 갱신 박혀있어 변동성 낮음).
 */

const TTL_MS = 30_000;
let cached: { ip: string; fetchedAt: number } | null = null;
let inflight: Promise<string | null> | null = null;

export function isMobileDevice(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /iPhone|iPad|iPod|Android|Mobile/i.test(navigator.userAgent);
}

export async function getMobileHelperBase(): Promise<string | null> {
  if (!isMobileDevice()) return null;
  const now = Date.now();
  if (cached && now - cached.fetchedAt < TTL_MS) {
    return cached.ip || null;
  }
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const res = await fetch('/api/helper/lan-ip', {
        method: 'GET',
        credentials: 'include',
      });
      if (!res.ok) return null;
      const body = (await res.json()) as { result?: number; data?: { lanIp?: string } };
      const ip = body?.data?.lanIp || '';
      cached = { ip, fetchedAt: now };
      return ip || null;
    } catch {
      return null;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}
