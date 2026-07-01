"""Integration tests: HTTP round-trip through the FastAPI server.

Uses FastAPI's TestClient (backed by httpx) to test the full
ingest → store → query pipeline without starting a real server.
"""

import pytest
from fastapi.testclient import TestClient

from sonar.ingestion.server import app, trace_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_store():
    """Clear the trace store before each test."""
    trace_store.clear()
    yield
    trace_store.clear()


@pytest.fixture()
def client():
    """Provide a synchronous TestClient for the FastAPI app."""
    return TestClient(app)


def _build_payload(
    trace_id: str = "a" * 32,
    spans: list[dict] | None = None,
    service_name: str = "test-svc",
) -> dict:
    """Build a minimal valid OTLP JSON payload."""
    if spans is None:
        spans = [{
            "traceId": trace_id,
            "spanId": "b" * 16,
            "parentSpanId": "",
            "name": "test-span",
            "startTimeUnixNano": "1000000",
            "endTimeUnixNano": "2000000",
            "status": {"code": 1},
            "attributes": [],
        }]
    return {
        "resourceSpans": [{
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": service_name}}
                ]
            },
            "scopeSpans": [{
                "scope": {"name": "test"},
                "spans": spans,
            }],
        }]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIngestTraces:
    """POST /v1/traces endpoint."""

    def test_ingest_single_span(self, client):
        resp = client.post("/v1/traces", json=_build_payload())
        assert resp.status_code == 200
        assert resp.json()["accepted_spans"] == 1

    def test_ingest_stores_in_trace_store(self, client):
        client.post("/v1/traces", json=_build_payload())
        assert len(trace_store) == 1

    def test_ingest_multiple_spans(self, client):
        payload = _build_payload(spans=[
            {
                "traceId": "a" * 32,
                "spanId": "1" * 16,
                "parentSpanId": "",
                "name": "root",
                "startTimeUnixNano": "0",
                "endTimeUnixNano": "5000000",
                "attributes": [],
            },
            {
                "traceId": "a" * 32,
                "spanId": "2" * 16,
                "parentSpanId": "1" * 16,
                "name": "child",
                "startTimeUnixNano": "1000000",
                "endTimeUnixNano": "3000000",
                "attributes": [],
            },
        ])
        resp = client.post("/v1/traces", json=payload)
        assert resp.json()["accepted_spans"] == 2

    def test_malformed_payload_returns_400(self, client):
        resp = client.post(
            "/v1/traces",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_empty_resource_spans(self, client):
        resp = client.post("/v1/traces", json={"resourceSpans": []})
        assert resp.status_code == 200
        assert resp.json()["accepted_spans"] == 0


class TestListTraces:
    """GET /traces endpoint."""

    def test_empty_store(self, client):
        resp = client.get("/traces")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_after_ingest(self, client):
        client.post("/v1/traces", json=_build_payload())
        resp = client.get("/traces")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["trace_id"] == "a" * 32
        assert data[0]["span_count"] == 1
        assert data[0]["root_span_name"] == "test-span"


class TestGetTraceTree:
    """GET /traces/{trace_id} endpoint."""

    def test_not_found(self, client):
        resp = client.get("/traces/nonexistent")
        assert resp.status_code == 404

    def test_tree_structure(self, client):
        payload = _build_payload(spans=[
            {
                "traceId": "a" * 32,
                "spanId": "1" * 16,
                "parentSpanId": "",
                "name": "root",
                "startTimeUnixNano": "0",
                "endTimeUnixNano": "5000000",
                "attributes": [],
            },
            {
                "traceId": "a" * 32,
                "spanId": "2" * 16,
                "parentSpanId": "1" * 16,
                "name": "child",
                "startTimeUnixNano": "1000000",
                "endTimeUnixNano": "3000000",
                "attributes": [],
            },
        ])
        client.post("/v1/traces", json=payload)

        resp = client.get(f"/traces/{'a' * 32}")
        data = resp.json()
        assert data["span_count"] == 2
        assert len(data["tree"]) == 1  # Single root.
        root = data["tree"][0]
        assert root["span"]["name"] == "root"
        assert len(root["children"]) == 1
        assert root["children"][0]["span"]["name"] == "child"

    def test_tree_includes_duration_ms(self, client):
        client.post("/v1/traces", json=_build_payload())
        resp = client.get(f"/traces/{'a' * 32}")
        root = resp.json()["tree"][0]
        assert "duration_ms" in root["span"]
        assert root["span"]["duration_ms"] == 1.0


class TestRoundTrip:
    """Full round-trip: ingest → list → get tree."""

    def test_full_pipeline(self, client):
        # 1. Ingest.
        payload = _build_payload(service_name="gateway")
        resp = client.post("/v1/traces", json=payload)
        assert resp.json()["accepted_spans"] == 1

        # 2. List.
        traces = client.get("/traces").json()
        assert len(traces) == 1
        trace_id = traces[0]["trace_id"]

        # 3. Get tree.
        tree = client.get(f"/traces/{trace_id}").json()
        assert tree["span_count"] == 1
        assert tree["tree"][0]["span"]["service_name"] == "gateway"
