"""settings 통합 테스트 — a2a_workspace / workrole_file get/put + code-server."""
from app.settings.models import AideskSetting


def _login(client) -> dict:
    client.post("/api/auth/signup", json={"loginId": "alice@example.com", "password": "passw0rd"})
    rs = client.post("/api/auth/authenticate", json={"loginId": "alice@example.com", "password": "passw0rd"})
    return dict(rs.cookies)


def test_get_a2a_workspace_default_empty(client):
    cookies = _login(client)
    rs = client.get("/api/settings/a2a-workspace", cookies=cookies)
    assert rs.status_code == 200
    assert rs.json()["data"] == {"path": ""}


def test_put_a2a_workspace_then_get(client, db_session):
    cookies = _login(client)
    rs = client.put(
        "/api/settings/a2a-workspace",
        json={"path": "/Users/jsh/workspace/me", "purgePreviousHistory": False},
        cookies=cookies,
    )
    assert rs.status_code == 200
    assert rs.json()["data"]["path"] == "/Users/jsh/workspace/me"

    rs = client.get("/api/settings/a2a-workspace", cookies=cookies)
    assert rs.json()["data"]["path"] == "/Users/jsh/workspace/me"

    # DB row 검증
    row = db_session.query(AideskSetting).filter_by(setting_key="a2a_workspace").one()
    assert row.setting_value == "/Users/jsh/workspace/me"


def test_put_a2a_workspace_empty_returns_fail(client):
    cookies = _login(client)
    rs = client.put(
        "/api/settings/a2a-workspace",
        json={"path": "", "purgePreviousHistory": False},
        cookies=cookies,
    )
    assert rs.json()["result"] == 1


def test_workrole_file_get_put(client, db_session):
    cookies = _login(client)
    # default = empty
    rs = client.get("/api/settings/workrole-file", cookies=cookies)
    assert rs.json()["data"] == {"path": ""}

    # put
    rs = client.put(
        "/api/settings/workrole-file",
        json={"path": "/path/to/workrole.md"},
        cookies=cookies,
    )
    assert rs.status_code == 200
    assert rs.json()["data"]["path"] == "/path/to/workrole.md"

    # get
    rs = client.get("/api/settings/workrole-file", cookies=cookies)
    assert rs.json()["data"]["path"] == "/path/to/workrole.md"


def test_settings_require_auth(client):
    rs = client.get("/api/settings/a2a-workspace")
    assert rs.status_code == 401
    assert rs.json()["code"] == "NA"


def test_code_server_empty_url(client):
    cookies = _login(client)
    rs = client.get("/api/settings/code-server", cookies=cookies)
    # config.code_server_url 가 빈 값 = url 빈 + alive False
    body = rs.json()
    assert body["result"] == 0
    assert body["data"] == {"url": "", "alive": False}


def test_settings_user_isolation(client, db_session):
    """다른 user 가 put 한 값이 본인 get 에 안 보이는지."""
    cookies_a = _login(client)
    client.put(
        "/api/settings/a2a-workspace",
        json={"path": "/tmp/alice", "purgePreviousHistory": False},
        cookies=cookies_a,
    )

    # 새 user
    client.post("/api/auth/signup", json={"loginId": "bob@example.com", "password": "passw0rd"})
    rs_b = client.post("/api/auth/authenticate", json={"loginId": "bob@example.com", "password": "passw0rd"})
    cookies_b = dict(rs_b.cookies)

    rs = client.get("/api/settings/a2a-workspace", cookies=cookies_b)
    # bob 은 아무 setting 없음
    assert rs.json()["data"]["path"] == ""
