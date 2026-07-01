"""Tests for sonar.ingestion.store.TraceStore."""

import threading

import pytest

from sonar.ingestion.models import Span
from sonar.ingestion.store import TraceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(
    span_id: str = "s1",
    trace_id: str = "t1",
    **kwargs,
) -> Span:
    """Create a minimal Span for testing."""
    defaults = {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": None,
        "name": "op",
        "service_name": "svc",
        "start_time": 0,
        "end_time": 1_000_000,
    }
    defaults.update(kwargs)
    return Span(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTraceStoreBasic:
    """Basic CRUD operations."""

    def test_empty_store(self):
        store = TraceStore()
        assert len(store) == 0
        assert store.trace_ids() == set()
        assert store.all_traces() == []

    def test_add_single_span(self):
        store = TraceStore()
        store.add_spans([_make_span()])
        assert len(store) == 1
        assert "t1" in store

    def test_get_trace(self):
        store = TraceStore()
        span = _make_span()
        store.add_spans([span])
        result = store.get_trace("t1")
        assert result is not None
        assert len(result) == 1
        assert result[0].span_id == "s1"

    def test_get_missing_trace(self):
        store = TraceStore()
        assert store.get_trace("missing") is None

    def test_multiple_spans_same_trace(self):
        store = TraceStore()
        store.add_spans([
            _make_span(span_id="s1", trace_id="t1"),
            _make_span(span_id="s2", trace_id="t1"),
        ])
        assert len(store) == 1
        result = store.get_trace("t1")
        assert len(result) == 2

    def test_multiple_traces(self):
        store = TraceStore()
        store.add_spans([
            _make_span(span_id="s1", trace_id="t1"),
            _make_span(span_id="s2", trace_id="t2"),
        ])
        assert len(store) == 2
        assert store.trace_ids() == {"t1", "t2"}

    def test_clear(self):
        store = TraceStore()
        store.add_spans([_make_span()])
        store.clear()
        assert len(store) == 0

    def test_all_traces_returns_copies(self):
        """Modifying returned lists must not affect internal state."""
        store = TraceStore()
        store.add_spans([_make_span()])
        traces = store.all_traces()
        traces.clear()
        assert len(store) == 1  # Internal state unchanged.

    def test_get_trace_returns_copy(self):
        """Modifying returned list must not affect internal state."""
        store = TraceStore()
        store.add_spans([_make_span()])
        result = store.get_trace("t1")
        result.clear()
        assert len(store.get_trace("t1")) == 1


class TestTraceStoreEviction:
    """FIFO eviction when exceeding max_traces."""

    def test_eviction_at_limit(self):
        store = TraceStore(max_traces=3)
        for i in range(5):
            store.add_spans([_make_span(span_id=f"s{i}", trace_id=f"t{i}")])

        assert len(store) == 3
        # Oldest two (t0, t1) should be evicted.
        assert "t0" not in store
        assert "t1" not in store
        assert "t2" in store
        assert "t3" in store
        assert "t4" in store

    def test_updating_existing_trace_does_not_evict(self):
        store = TraceStore(max_traces=2)
        store.add_spans([_make_span(span_id="s1", trace_id="t1")])
        store.add_spans([_make_span(span_id="s2", trace_id="t2")])
        # Add another span to t1 — should not evict since trace count stays 2.
        store.add_spans([_make_span(span_id="s3", trace_id="t1")])
        assert len(store) == 2
        assert len(store.get_trace("t1")) == 2

    def test_insertion_order_after_update(self):
        """Updating a trace moves it to the end (most recent)."""
        store = TraceStore(max_traces=2)
        store.add_spans([_make_span(span_id="s1", trace_id="t1")])
        store.add_spans([_make_span(span_id="s2", trace_id="t2")])
        # Touch t1 — should move to end.
        store.add_spans([_make_span(span_id="s3", trace_id="t1")])
        # Now add t3 — should evict t2 (oldest), not t1.
        store.add_spans([_make_span(span_id="s4", trace_id="t3")])
        assert "t2" not in store
        assert "t1" in store
        assert "t3" in store


class TestTraceStoreContains:
    """__contains__ check."""

    def test_contains_true(self):
        store = TraceStore()
        store.add_spans([_make_span(trace_id="t1")])
        assert "t1" in store

    def test_contains_false(self):
        store = TraceStore()
        assert "missing" not in store


class TestTraceStoreThreadSafety:
    """Concurrent access should not raise errors."""

    def test_concurrent_add_and_read(self):
        store = TraceStore(max_traces=100)
        errors: list[Exception] = []

        def writer():
            try:
                for i in range(200):
                    store.add_spans([
                        _make_span(span_id=f"w-{i}", trace_id=f"tw-{i}")
                    ])
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(200):
                    store.all_traces()
                    store.trace_ids()
                    len(store)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Thread safety errors: {errors}"
