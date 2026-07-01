"""Data models for OpenTelemetry span and trace representations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Span:
    """Represents a single OpenTelemetry span.

    A span tracks a unit of work within a distributed trace. Each span
    has a unique span_id and belongs to a trace identified by trace_id.
    Child spans reference their parent via parent_span_id.

    Attributes:
        span_id: Unique identifier for this span.
        trace_id: Identifier for the trace this span belongs to.
        parent_span_id: Identifier of the parent span, or None for root spans.
        name: Human-readable name describing the operation (e.g. "POST /checkout").
        service_name: Name of the service that generated this span.
        start_time: Span start time in nanoseconds since epoch.
        end_time: Span end time in nanoseconds since epoch.
        status: Span status — either "OK" or "ERROR".
        attributes: Arbitrary key-value metadata attached to the span.
    """

    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    service_name: str
    start_time: int
    end_time: int
    status: str = "OK"
    attributes: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Calculate span duration in milliseconds."""
        return (self.end_time - self.start_time) / 1_000_000
