/**
 * Open-redirect 차단 whitelist — runtime config (ConfigMap-주입 `__APP_CONFIG__.allowedHosts`).
 * 환경변수 단일 진실 — 코드에 도메인 hardcode 없음. 미설정 시 모두 차단 (안전 default).
 *
 * `allowedHosts` = comma-separated suffix list (e.g. ".kaflix.internal,.kaflix.local").
 * Subdomain endsWith 매칭 — `aidesk.kaflix.internal` 같은 subdomain 까지 허용.
 * Spec 가 점 없이 와도 정규화해 `.<domain>` 으로 처리 — `evilkaflix.internal` 같은 prefix 매칭 사고 방지.
 */
export function isExternalRedirectAllowed(hostname: string): boolean {
  if (import.meta.server) return false;
  const cfg = (window as unknown as { __APP_CONFIG__?: { allowedHosts?: string } }).__APP_CONFIG__;
  const hosts = (cfg?.allowedHosts ?? '').split(',').map(s => s.trim()).filter(Boolean);
  if (hosts.length === 0) return false;
  const probe = '.' + hostname.toLowerCase();
  return hosts.some(h => probe.endsWith((h.startsWith('.') ? h : '.' + h).toLowerCase()));
}
