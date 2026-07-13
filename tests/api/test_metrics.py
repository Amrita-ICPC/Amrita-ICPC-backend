"""Tests for Prometheus metrics endpoint."""

from fastapi.testclient import TestClient

from app.main import fastapi_app


def test_metrics_endpoint() -> None:
    """Verify that the /metrics endpoint is exposed and publicly accessible."""
    client = TestClient(fastapi_app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
    # Check that prometheus metrics content-type is returned
    assert "text/plain" in response.headers.get("content-type", "")
