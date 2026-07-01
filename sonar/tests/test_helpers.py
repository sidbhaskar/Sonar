"""Tests for UI helper functions in sonar.ui.app."""

import pytest

from sonar.ingestion.models import Span
from sonar.core.tree_builder import TreeNode
from sonar.ui.app import detect_protocol, has_error, _subtree_has_error, format_span_label


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(
    status: str = "OK",
    attributes: dict | None = None,
    **kwargs,
) -> Span:
    """Create a Span with sensible defaults."""
    defaults = {
        "span_id": "s1",
        "trace_id": "t1",
        "parent_span_id": None,
        "name": "test-op",
        "service_name": "test-svc",
        "start_time": 0,
        "end_time": 1_000_000,
        "status": status,
        "attributes": attributes or {},
    }
    defaults.update(kwargs)
    return Span(**defaults)


# ---------------------------------------------------------------------------
# detect_protocol
# ---------------------------------------------------------------------------

class TestDetectProtocol:
    """Detect protocol type from span attributes."""

    def test_grpc(self):
        span = _make_span(attributes={"rpc.system": "grpc"})
        assert detect_protocol(span) == "grpc"

    def test_kafka(self):
        span = _make_span(attributes={"messaging.system": "kafka"})
        assert detect_protocol(span) == "kafka"

    def test_http_method(self):
        span = _make_span(attributes={"http.method": "GET"})
        assert detect_protocol(span) == "http"

    def test_http_route(self):
        span = _make_span(attributes={"http.route": "/api/v1/test"})
        assert detect_protocol(span) == "http"

    def test_unknown(self):
        span = _make_span(attributes={"db.system": "postgresql"})
        assert detect_protocol(span) is None

    def test_empty_attributes(self):
        span = _make_span(attributes={})
        assert detect_protocol(span) is None

    def test_grpc_takes_priority_over_http(self):
        """If both rpc.system and http.* exist, gRPC wins (checked first)."""
        span = _make_span(attributes={
            "rpc.system": "grpc",
            "http.method": "POST",
        })
        assert detect_protocol(span) == "grpc"


# ---------------------------------------------------------------------------
# has_error
# ---------------------------------------------------------------------------

class TestHasError:
    """Check if any span in a list has ERROR status."""

    def test_no_errors(self):
        spans = [_make_span(status="OK"), _make_span(status="OK")]
        assert has_error(spans) is False

    def test_one_error(self):
        spans = [_make_span(status="OK"), _make_span(status="ERROR")]
        assert has_error(spans) is True

    def test_all_errors(self):
        spans = [_make_span(status="ERROR"), _make_span(status="ERROR")]
        assert has_error(spans) is True

    def test_empty_list(self):
        assert has_error([]) is False


# ---------------------------------------------------------------------------
# _subtree_has_error
# ---------------------------------------------------------------------------

class TestSubtreeHasError:
    """Check if a node or any descendant has ERROR status."""

    def test_leaf_ok(self):
        node = TreeNode(span=_make_span(status="OK"))
        assert _subtree_has_error(node) is False

    def test_leaf_error(self):
        node = TreeNode(span=_make_span(status="ERROR"))
        assert _subtree_has_error(node) is True

    def test_child_error(self):
        child = TreeNode(span=_make_span(status="ERROR", span_id="c1"))
        parent = TreeNode(span=_make_span(status="OK"), children=[child])
        assert _subtree_has_error(parent) is True

    def test_deep_descendant_error(self):
        grandchild = TreeNode(span=_make_span(status="ERROR", span_id="gc"))
        child = TreeNode(span=_make_span(status="OK", span_id="c"), children=[grandchild])
        root = TreeNode(span=_make_span(status="OK"), children=[child])
        assert _subtree_has_error(root) is True

    def test_all_ok_subtree(self):
        child = TreeNode(span=_make_span(status="OK", span_id="c"))
        root = TreeNode(span=_make_span(status="OK"), children=[child])
        assert _subtree_has_error(root) is False


# ---------------------------------------------------------------------------
# format_span_label
# ---------------------------------------------------------------------------

class TestFormatSpanLabel:
    """Build Rich Text labels for span tree nodes."""

    def test_ok_span_contains_name(self):
        span = _make_span(name="POST /checkout")
        label = format_span_label(span)
        assert "POST /checkout" in label.plain

    def test_ok_span_contains_service(self):
        span = _make_span(service_name="api-gateway")
        label = format_span_label(span)
        assert "(api-gateway)" in label.plain

    def test_ok_span_contains_duration(self):
        span = _make_span(start_time=0, end_time=812_000_000)
        label = format_span_label(span)
        assert "812ms" in label.plain

    def test_error_span_has_marker(self):
        span = _make_span(status="ERROR")
        label = format_span_label(span)
        assert "✕" in label.plain

    def test_ok_span_no_error_marker(self):
        span = _make_span(status="OK")
        label = format_span_label(span, descendant_error=False)
        assert "✕" not in label.plain
        assert "!" not in label.plain

    def test_descendant_error_has_propagation_marker(self):
        span = _make_span(status="OK")
        label = format_span_label(span, descendant_error=True)
        assert "!" in label.plain

    def test_protocol_badge_http(self):
        span = _make_span(attributes={"http.method": "GET"})
        label = format_span_label(span)
        assert "[http]" in label.plain

    def test_protocol_badge_grpc(self):
        span = _make_span(attributes={"rpc.system": "grpc"})
        label = format_span_label(span)
        assert "[grpc]" in label.plain

    def test_protocol_badge_kafka(self):
        span = _make_span(attributes={"messaging.system": "kafka"})
        label = format_span_label(span)
        assert "[kafka]" in label.plain

    def test_no_protocol_no_badge(self):
        span = _make_span(attributes={"db.system": "postgresql"})
        label = format_span_label(span)
        assert "[http]" not in label.plain
        assert "[grpc]" not in label.plain
        assert "[kafka]" not in label.plain
