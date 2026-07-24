from fastapi.testclient import TestClient

from app.main import app


def test_metrics_endpoint_exposes_prometheus_metrics() -> None:
    with TestClient(app) as client:
        client.get("/healthz")
        dynamic_route_resp = client.get("/api/providers/not-a-provider")
        resp = client.get("/metrics")

    assert dynamic_route_resp.status_code == 401
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
