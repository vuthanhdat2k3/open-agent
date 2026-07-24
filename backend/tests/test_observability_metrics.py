from fastapi.testclient import TestClient

from app.main import app


def test_metrics_endpoint_exposes_prometheus_metrics() -> None:
    with TestClient(app) as client:
        client.get("/healthz")
        resp = client.get("/metrics")

    assert resp.status_code == 200
    assert "http_requests_total" in resp.text

