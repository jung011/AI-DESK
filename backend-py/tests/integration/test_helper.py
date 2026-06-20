"""helper 통합 테스트 — /version + /download. tmp 디렉토리에 .pkg 생성 + helper_pkg_dir 주입."""
import os

import pytest

from app.core.config import get_settings


def _login(client) -> dict:
    client.post("/api/auth/signup", json={"loginId": "alice@example.com", "password": "passw0rd"})
    rs = client.post("/api/auth/authenticate", json={"loginId": "alice@example.com", "password": "passw0rd"})
    return dict(rs.cookies)


@pytest.fixture
def helper_pkg_dir(tmp_path, monkeypatch):
    """tmp 디렉토리 안 가짜 .pkg 파일 + settings.helper_pkg_dir override."""
    pkg = tmp_path / "AIDeskHelper-0.8.9-arm64.pkg"
    pkg.write_bytes(b"FAKE PKG CONTENT")
    monkeypatch.setattr(get_settings(), "helper_pkg_dir", str(tmp_path))
    return tmp_path


def test_helper_version_returns_parsed(client, helper_pkg_dir):
    cookies = _login(client)
    rs = client.get("/api/helper/version", cookies=cookies)
    assert rs.status_code == 200
    body = rs.json()
    assert body["result"] == 0
    assert body["data"]["latest"] == "0.8.9"
    assert body["data"]["filename"] == "AIDeskHelper-0.8.9-arm64.pkg"


def test_helper_version_no_pkg_returns_empty(client, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "helper_pkg_dir", str(tmp_path))
    cookies = _login(client)
    rs = client.get("/api/helper/version", cookies=cookies)
    body = rs.json()
    assert body["data"] == {"latest": "", "filename": ""}


def test_helper_download_serves_pkg(client, helper_pkg_dir):
    cookies = _login(client)
    rs = client.get("/api/helper/download", cookies=cookies)
    assert rs.status_code == 200
    assert rs.content == b"FAKE PKG CONTENT"
    cd = rs.headers["content-disposition"]
    assert "AIDeskHelper-0.8.9-arm64.pkg" in cd


def test_helper_download_no_pkg_returns_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "helper_pkg_dir", str(tmp_path))
    cookies = _login(client)
    rs = client.get("/api/helper/download", cookies=cookies)
    assert rs.status_code == 404


def test_helper_endpoints_require_auth(client):
    rs = client.get("/api/helper/version")
    assert rs.status_code == 401
    assert rs.json()["code"] == "NA"
