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


def set_auth_cookie(response: Response, name: str, value: str, max_age_seconds: int) -> None:
    """access/refresh 토큰을 쿠키로 발급. domain 명시 시 host-only 잔재 cleanup 함께."""
    response.headers.append(
        "Set-Cookie",
        _build_cookie_header(name, value, max_age_seconds, settings.cookie_secure, settings.cookie_domain or None),
    )
    if settings.cookie_domain:
        # host-only 잔재 cookie cleanup (Spring CookieUtil 와 동일 패턴)
        response.headers.append(
            "Set-Cookie",
            _build_cookie_header(name, "", 0, settings.cookie_secure, None),
        )


def clear_auth_cookie(response: Response, name: str) -> None:
    """sign-out / refresh fail 시 쿠키 즉시 expire."""
    response.headers.append(
        "Set-Cookie",
        _build_cookie_header(name, "", 0, settings.cookie_secure, settings.cookie_domain or None),
    )
    if settings.cookie_domain:
        response.headers.append(
            "Set-Cookie",
            _build_cookie_header(name, "", 0, settings.cookie_secure, None),
        )
