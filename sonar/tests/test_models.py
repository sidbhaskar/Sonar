"""Tests for sonar.ingestion.models.Span."""

import pytest

from sonar.ingestion.models import Span


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(
    start_time: int = 0,
    end_time: int = 1_000_000,
    **kwargs,
) -> Span:
    """Create a Span with sensible defaults."""
    defaults = {
        "span_id": "abc123",
        "trace_id": "trace-1",
        "parent_span_id": None,
        "name": "test-op",
        "service_name": "test-svc",
        "start_time": start_time,
        "end_time": end_time,
    }
    defaults.update(kwargs)
    return Span(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSpanDurationMs:
    """Span.duration_ms property."""

    def test_one_millisecond(self):
        span = _make_span(start_time=0, end_time=1_000_000)
        assert span.duration_ms == 1.0

    def test_zero_duration(self):
        span = _make_span(start_time=5_000_000, end_time=5_000_000)
        assert span.duration_ms == 0.0

    def test_sub_millisecond(self):
        span = _make_span(start_time=0, end_time=500_000)
        assert span.duration_ms == 0.5

    def test_large_duration(self):
        span = _make_span(start_time=0, end_time=812_000_000)
        assert span.duration_ms == 812.0


class TestSpanDefaults:
    """Default values for optional fields."""

    def test_default_status_is_ok(self):
        span = _make_span()
        assert span.status == "OK"

    def test_default_attributes_is_empty_dict(self):
        span = _make_span()
        assert span.attributes == {}

    def test_custom_status(self):
        span = _make_span(status="ERROR")
        assert span.status == "ERROR"

    def test_custom_attributes(self):
        attrs = {"http.method": "GET", "http.status_code": 200}
        span = _make_span(attributes=attrs)
        assert span.attributes == attrs
