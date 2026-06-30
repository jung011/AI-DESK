"""인증 쿠키 helper — Spring 의 CookieUtil 와 동일 형식 (이름, 옵션, host-only cleanup).

Set-Cookie: <name>=<value>; Path=/; Max-Age=<sec>; HttpOnly; SameSite=Lax[; Secure][; Domain=...]

domain 명시 발급 시 host-only 잔재 cookie 가 충돌해 first-match 으로 잘못 채택되는 사고
방지를 위해 *host-only 변형도 Max-Age=0* 으로 cleanup. RFC 6265 — 같은 이름이라도 Domain 이
다르면 별개 cookie 라 명시 expire 필요.
"""
from fastapi import Response

from app.core.config import get_settings

settings = get_settings()


def _build_cookie_header(
    name: str,
    value: str,
    max_age_seconds: int,
    secure: bool,
    domain: str | None,
) -> str:
    parts = [f"{name}={value}", "Path=/", f"Max-Age={max_age_seconds}", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    if domain:
        parts.append(f"Domain={domain}")
    return "; ".join(parts)


# 옵션 B 전환 cleanup — 옛 cookieDomain=".kaflix.internal" 박혀있던 사용자 가 새
# cookieDomain="" 박힌 후 *옛 Domain 쿠키 cleanup 안 박혀* refresh 시 OLD 쿠키 send →
# backend 가 family revoke → 1 시간 마다 logout 사고. 모든 cookieDomain 전환 시 *역방향
# 도 cleanup* 박는 게 정합. 호환 cookie domain 변수 — set 박을 때 cleanup 박을 모든 variant.
_LEGACY_DOMAIN = ".kaflix.internal"


def set_auth_cookie(response: Response, name: str, value: str, max_age_seconds: int) -> None:
    """access/refresh 토큰을 쿠키로 발급.

    cleanup 박는 거:
    - 현재 cookie_domain 박혀있을 때: host-only 잔재 expire
    - 현재 cookie_domain 비어있을 때: Domain=.kaflix.internal 잔재 expire (옵션 B 전환)
    """
    current_domain = settings.cookie_domain or None
    response.headers.append(
        "Set-Cookie",
        _build_cookie_header(name, value, max_age_seconds, settings.cookie_secure, current_domain),
    )
    # cleanup — 현재 variant 외 *다른 variant 모두 expire*. 한 cookie name 의 두 variant
    # 가 browser 에 공존 박는 사고 차단.
    if current_domain:
        # host-only 잔재 expire
        response.headers.append(
            "Set-Cookie",
            _build_cookie_header(name, "", 0, settings.cookie_secure, None),
        )
    elif _LEGACY_DOMAIN:
        # Domain=.kaflix.internal 잔재 expire (옛 cookieDomain 전환 호환)
        response.headers.append(
            "Set-Cookie",
            _build_cookie_header(name, "", 0, settings.cookie_secure, _LEGACY_DOMAIN),
        )


def clear_auth_cookie(response: Response, name: str) -> None:
    """sign-out / refresh fail 시 쿠키 즉시 expire. 모든 variant 도 같이 정리."""
    current_domain = settings.cookie_domain or None
    response.headers.append(
        "Set-Cookie",
        _build_cookie_header(name, "", 0, settings.cookie_secure, current_domain),
    )
    if current_domain:
        response.headers.append(
            "Set-Cookie",
            _build_cookie_header(name, "", 0, settings.cookie_secure, None),
        )
    elif _LEGACY_DOMAIN:
        response.headers.append(
            "Set-Cookie",
            _build_cookie_header(name, "", 0, settings.cookie_secure, _LEGACY_DOMAIN),
        )
