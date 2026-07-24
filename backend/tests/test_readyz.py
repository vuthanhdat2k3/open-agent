from fastapi.testclient import TestClient

from app.main import app


def test_readyz_ok(monkeypatch) -> None:
    async def ok() -> None:
        return None

    monkeypatch.setattr("app.main._check_db", ok)
    monkeypatch.setattr("app.main._check_redis", ok)

    with TestClient(app) as client:
        resp = client.get("/readyz")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_readyz_returns_503_when_dependency_fails(monkeypatch) -> None:
    async def ok() -> None:
        return None

    async def fail() -> None:
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.main._check_db", ok)
    monkeypatch.setattr("app.main._check_redis", fail)

    with TestClient(app) as client:
        resp = client.get("/readyz")

    assert resp.status_code == 503
    assert resp.json()["detail"]["status"] == "unready"
    assert "redis down" in resp.json()["detail"]["checks"]["redis"]

