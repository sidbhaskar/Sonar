"""Thread-safe in-memory trace store with FIFO eviction.

Provides a ``TraceStore`` class that wraps a dict behind a
``threading.Lock`` so the FastAPI ingestion thread and the Textual
UI thread can safely share trace data without data races.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Iterator

from sonar.ingestion.models import Span


class TraceStore:
    """Thread-safe store for traces keyed by trace_id.

    Uses an ``OrderedDict`` internally so insertion order is preserved
    (newest trace is always last).  When the store exceeds ``max_traces``,
    the oldest traces are evicted automatically (FIFO).

    All public methods acquire the internal lock, so callers never need
    to think about synchronization.

    Args:
        max_traces: Maximum number of traces to retain.  Defaults to 500.
    """

    def __init__(self, max_traces: int = 500) -> None:
        self._lock = threading.Lock()
        self._traces: OrderedDict[str, list[Span]] = OrderedDict()
        self._max_traces = max_traces

    # ── Writes ────────────────────────────────────────────

    def add_spans(self, spans: list[Span]) -> None:
        """Add spans to the store, grouped by their trace_id.

        If adding new traces pushes the total count above ``max_traces``,
        the oldest traces are evicted to make room.

        Args:
            spans: A list of Span objects (may belong to multiple traces).
        """
        with self._lock:
            for span in spans:
                if span.trace_id in self._traces:
                    self._traces[span.trace_id].append(span)
                    # Move to end so it reflects the latest update time.
                    self._traces.move_to_end(span.trace_id)
                else:
                    self._traces[span.trace_id] = [span]

            # Evict oldest traces if over limit.
            while len(self._traces) > self._max_traces:
                self._traces.popitem(last=False)

    def clear(self) -> None:
        """Remove all traces from the store."""
        with self._lock:
            self._traces.clear()

    # ── Reads ─────────────────────────────────────────────

    def get_trace(self, trace_id: str) -> list[Span] | None:
        """Return the span list for a trace, or None if not found.

        Returns a *copy* of the list so the caller can iterate safely
        without holding the lock.
        """
        with self._lock:
            spans = self._traces.get(trace_id)
            return list(spans) if spans is not None else None

    def all_traces(self) -> list[tuple[str, list[Span]]]:
        """Return all (trace_id, spans) pairs, newest last.

        Returns shallow copies so iteration is safe outside the lock.
        """
        with self._lock:
            return [
                (tid, list(spans))
                for tid, spans in self._traces.items()
            ]

    def trace_ids(self) -> set[str]:
        """Return the set of all stored trace IDs."""
        with self._lock:
            return set(self._traces.keys())

    def __len__(self) -> int:
        """Return the number of stored traces."""
        with self._lock:
            return len(self._traces)

    def __contains__(self, trace_id: str) -> bool:
        """Check if a trace_id exists in the store."""
        with self._lock:
            return trace_id in self._traces
