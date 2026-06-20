"""auth 통합 테스트 — signup → authenticate → me → refresh → sign-out.

전체 flow 가 cookie + JWT + refresh rotation 까지 의도대로 작동하는지 검증.
"""
from app.agents.models import AiAgent
from app.auth.models import RefreshToken, User


def _signup(client, login_id: str = "alice@example.com", password: str = "passw0rd") -> dict:
    rs = client.post("/api/auth/signup", json={"loginId": login_id, "password": password})
    assert rs.status_code == 200, rs.text
    return rs.json()


def _login(client, login_id: str = "alice@example.com", password: str = "passw0rd") -> tuple[dict, dict]:
    """authenticate + cookie 추출."""
    rs = client.post("/api/auth/authenticate", json={"loginId": login_id, "password": password})
    assert rs.status_code == 200, rs.text
    return rs.json(), rs.cookies


def test_signup_creates_user_and_human_entity(client, db_session):
    rs = _signup(client)
    assert rs["result"] == 0
    assert rs["data"]["loginId"] == "alice@example.com"
    assert rs["data"]["role"] == "USER"
    assert rs["data"]["displayName"] == "alice@example.com"
    account_sn = rs["data"]["accountSn"]

    user = db_session.query(User).filter_by(account_sn=account_sn).one()
    assert user.login_id == "alice@example.com"
    assert user.password != "passw0rd"  # bcrypt 해시

    # 휴먼 entity 자동 생성 검증
    human = db_session.query(AiAgent).filter_by(owner_account_sn=account_sn, model="human").one()
    assert human.agent_name == "휴먼"
    assert human.tmux_session == f"__human__:{account_sn}"


def test_signup_duplicate_returns_409(client):
    _signup(client)
    rs = client.post(
        "/api/auth/signup",
        json={"loginId": "alice@example.com", "password": "another"},
    )
    assert rs.status_code == 200  # envelope status
    body = rs.json()
    assert body["result"] == 409


def test_signup_normalizes_login_id(client, db_session):
    rs = client.post(
        "/api/auth/signup",
        json={"loginId": "Alice@EXAMPLE.com", "password": "passw0rd"},
    )
    assert rs.json()["data"]["loginId"] == "alice@example.com"


def test_authenticate_success_sets_cookies_and_record_last_login(client, db_session):
    _signup(client)
    body, cookies = _login(client)
    assert body["result"] == 0
    assert "accessToken" in cookies
    assert "refreshToken" in cookies
    assert body["data"]["loginId"] == "alice@example.com"

    user = db_session.query(User).filter_by(login_id="alice@example.com").one()
    assert user.last_login_dt is not None

    # refresh token DB row
    tokens = db_session.query(RefreshToken).filter_by(login_id="alice@example.com").all()
    assert len(tokens) == 1
    assert tokens[0].revoked_yn == "N"


def test_authenticate_wrong_password_returns_401(client):
    _signup(client)
    rs = client.post(
        "/api/auth/authenticate",
        json={"loginId": "alice@example.com", "password": "wrong"},
    )
    assert rs.json()["result"] == 401


def test_me_requires_auth(client):
    rs = client.get("/api/auth/me")
    # NotAuthenticated → 401 + {code: "NA"}
    assert rs.status_code == 401
    assert rs.json() == {"code": "NA", "message": "Not authenticated"}


def test_me_with_cookie_returns_account(client):
    _signup(client)
    _, cookies = _login(client)
    rs = client.get("/api/auth/me", cookies=dict(cookies))
    assert rs.status_code == 200
    body = rs.json()
    assert body["result"] == 0
    assert body["data"]["loginId"] == "alice@example.com"
    assert body["data"]["lastLoginDt"] is not None


def test_refresh_rotation_revokes_old_and_issues_new(client, db_session):
    _signup(client)
    _, cookies = _login(client)
    old_refresh = cookies["refreshToken"]

    rs = client.post("/api/auth/refresh", cookies={"refreshToken": old_refresh})
    assert rs.status_code == 200
    body = rs.json()
    assert body["result"] == 0
    new_refresh = rs.cookies["refreshToken"]
    assert new_refresh != old_refresh

    # 옛 token 의 jti 가 revoked_yn=Y, 새 jti 가 revoked_yn=N 인지 검증
    tokens = db_session.query(RefreshToken).filter_by(login_id="alice@example.com").all()
    assert len(tokens) == 2
    revoked = [t for t in tokens if t.revoked_yn == "Y"]
    active = [t for t in tokens if t.revoked_yn == "N"]
    assert len(revoked) == 1
    assert len(active) == 1
    # 같은 family
    assert revoked[0].family_id == active[0].family_id


def test_refresh_reuse_revokes_family(client, db_session):
    """옛 refresh 두 번 사용 = reuse → family 전체 폐기."""
    _signup(client)
    _, cookies = _login(client)
    old_refresh = cookies["refreshToken"]

    # 첫 rotation — 정상
    client.post("/api/auth/refresh", cookies={"refreshToken": old_refresh})

    # 두 번째 — 옛 token 재사용 → reuse 감지 → family 폐기
    rs = client.post("/api/auth/refresh", cookies={"refreshToken": old_refresh})
    assert rs.json()["result"] == 401

    tokens = db_session.query(RefreshToken).filter_by(login_id="alice@example.com").all()
    # 모두 폐기
    assert all(t.revoked_yn == "Y" for t in tokens)


def test_sign_out_revokes_all_and_clears_cookies(client, db_session):
    _signup(client)
    _, cookies = _login(client)
    rs = client.post("/api/auth/sign-out", cookies=dict(cookies))
    assert rs.status_code == 200
    assert rs.json()["result"] == 0

    tokens = db_session.query(RefreshToken).filter_by(login_id="alice@example.com").all()
    assert all(t.revoked_yn == "Y" for t in tokens)
