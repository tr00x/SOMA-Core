"""
Regression for v2026.6.x fix #31 — dashboard auth via
SOMA_DASHBOARD_TOKEN env var.

Default behavior unchanged (no token → no auth, anyone on localhost
reaches every endpoint). When token is set, requests without a
matching ``Authorization: Bearer`` header or ``?token=`` query
param get 401.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client_with_token(monkeypatch, token: str):
    monkeypatch.setenv("SOMA_DASHBOARD_TOKEN", token)
    # Force re-import so the module-level app picks up the env var.
    import importlib
    from soma.dashboard import app as app_mod
    importlib.reload(app_mod)
    return TestClient(app_mod.app)


def test_no_token_means_no_auth(monkeypatch):
    """Default — without SOMA_DASHBOARD_TOKEN set, dashboard is
    open. Existing setups must keep working."""
    monkeypatch.delenv("SOMA_DASHBOARD_TOKEN", raising=False)
    import importlib
    from soma.dashboard import app as app_mod
    importlib.reload(app_mod)
    client = TestClient(app_mod.app)

    # Any endpoint should respond without auth.
    r = client.get("/healthz")
    assert r.status_code in (200, 404)  # endpoint may not exist; just not 401


def test_token_set_blocks_unauthenticated(monkeypatch):
    client = _client_with_token(monkeypatch, "secret-token-abc")
    r = client.get("/api/agents")
    assert r.status_code == 401
    assert "SOMA_DASHBOARD_TOKEN" in r.text


def test_bearer_header_authorizes(monkeypatch):
    client = _client_with_token(monkeypatch, "secret-token-abc")
    r = client.get(
        "/api/agents",
        headers={"Authorization": "Bearer secret-token-abc"},
    )
    # Endpoint may 200/404/422 depending on state — just NOT 401.
    assert r.status_code != 401


def test_query_param_authorizes(monkeypatch):
    client = _client_with_token(monkeypatch, "secret-token-abc")
    r = client.get("/api/agents?token=secret-token-abc")
    assert r.status_code != 401


def test_wrong_token_blocked(monkeypatch):
    client = _client_with_token(monkeypatch, "secret-token-abc")
    r = client.get(
        "/api/agents",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_static_path_bypasses_auth(monkeypatch):
    """Login UI must remain reachable so a user with wrong token can
    fix it; 401 on static assets would brick the SPA shell."""
    client = _client_with_token(monkeypatch, "secret-token-abc")
    r = client.get("/static/anything.css")
    # 404 is expected (file doesn't exist), but NOT 401.
    assert r.status_code != 401
