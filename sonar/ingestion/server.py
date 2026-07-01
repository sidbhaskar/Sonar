"""FastAPI server for OTLP HTTP trace ingestion.

Accepts OTLP/HTTP JSON payloads on POST /v1/traces, parses them into
Span objects, and stores them in a thread-safe TraceStore keyed by trace_id.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from opentelemetry.proto.trace.v1.trace_pb2 import TracesData
from google.protobuf.json_format import MessageToDict
import base64

from sonar.core.tree_builder import TreeNode, build_tree
from sonar.ingestion.models import Span
from sonar.ingestion.store import TraceStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared trace store (thread-safe, used by both server and UI)
# ---------------------------------------------------------------------------
trace_store = TraceStore(max_traces=500)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Sonar OTLP Ingestion",
    description="Local OpenTelemetry trace collector for Sonar TUI.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# OTLP JSON parsing helpers
# ---------------------------------------------------------------------------

def _extract_attribute_value(value_obj: dict[str, Any]) -> Any:
    """Extract a scalar value from an OTLP AnyValue wrapper.

    OTLP wraps every attribute value in a typed object like
    {"stringValue": "foo"} or {"intValue": "42"}.  This function
    unwraps it to a plain Python value.
    """
    if "stringValue" in value_obj:
        return value_obj["stringValue"]
    if "intValue" in value_obj:
        return int(value_obj["intValue"])
    if "boolValue" in value_obj:
        return value_obj["boolValue"]
    if "doubleValue" in value_obj:
        return float(value_obj["doubleValue"])
    if "arrayValue" in value_obj:
        return [
            _extract_attribute_value(v)
            for v in value_obj["arrayValue"].get("values", [])
        ]
    # Fallback: return the raw dict for kvlistValue or unknown types.
    return value_obj


def _parse_attributes(attrs: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert an OTLP attributes array into a flat dict."""
    return {
        attr["key"]: _extract_attribute_value(attr["value"])
        for attr in attrs
        if "key" in attr and "value" in attr
    }


def _extract_service_name(resource: dict[str, Any]) -> str:
    """Pull service.name from an OTLP resource block."""
    for attr in resource.get("attributes", []):
        if attr.get("key") == "service.name":
            return _extract_attribute_value(attr["value"])
    return "unknown"


def _parse_status(status_obj: dict[str, Any] | None) -> str:
    """Map OTLP status to 'OK' or 'ERROR'.

    OTLP status codes: 0 = UNSET, 1 = OK, 2 = ERROR.
    We treat UNSET and OK both as "OK".
    """
    if status_obj is None:
        return "OK"
    code = status_obj.get("code", 0)
    return "ERROR" if code in (2, "2", "STATUS_CODE_ERROR") else "OK"


def _normalize_id(id_str: str) -> str:
    """Normalize base64 IDs from Protobuf or hex IDs from JSON to hex strings."""
    if not id_str:
        return ""
    if len(id_str) not in (32, 16):
        try:
            return base64.b64decode(id_str + "===").hex()
        except Exception:
            pass
    return id_str


def parse_otlp_payload(payload: dict[str, Any]) -> list[Span]:
    """Parse an OTLP/HTTP JSON trace payload into a flat list of Spans.

    Walks the resourceSpans -> scopeSpans -> spans hierarchy, extracting
    service.name from each resource block and applying it to every span
    under that resource.

    Malformed spans (missing required fields) are skipped with a warning
    rather than crashing the entire request.

    Args:
        payload: The raw JSON body from POST /v1/traces.

    Returns:
        A list of Span dataclass instances.
    """
    spans: list[Span] = []

    for resource_span in payload.get("resourceSpans", []):
        resource = resource_span.get("resource", {})
        service_name = _extract_service_name(resource)

        for scope_span in resource_span.get("scopeSpans", []):
            for raw_span in scope_span.get("spans", []):
                try:
                    span_id = _normalize_id(raw_span.get("spanId", ""))
                    trace_id = _normalize_id(raw_span.get("traceId", ""))

                    if not span_id or not trace_id:
                        logger.warning(
                            "Skipping span with missing spanId or traceId: %s",
                            raw_span.get("name", "<unnamed>"),
                        )
                        continue

                    parent_id = raw_span.get("parentSpanId") or None
                    # OTLP sends empty string for no parent; normalise to None.
                    if parent_id == "":
                        parent_id = None
                    elif parent_id:
                        parent_id = _normalize_id(parent_id)

                    span = Span(
                        span_id=span_id,
                        trace_id=trace_id,
                        parent_span_id=parent_id,
                        name=raw_span.get("name", "unknown"),
                        service_name=service_name,
                        start_time=int(raw_span.get("startTimeUnixNano", 0)),
                        end_time=int(raw_span.get("endTimeUnixNano", 0)),
                        status=_parse_status(raw_span.get("status")),
                        attributes=_parse_attributes(
                            raw_span.get("attributes", [])
                        ),
                    )
                    spans.append(span)
                except Exception:
                    logger.warning(
                        "Failed to parse span: %s",
                        raw_span.get("name", "<unnamed>"),
                        exc_info=True,
                    )

    return spans


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/v1/traces")
async def ingest_traces(request: Request) -> JSONResponse:
    """Accept an OTLP/HTTP trace export and store parsed spans.

    Mirrors the standard OTLP HTTP receiver endpoint so OTel agents
    can point their exporter at ``http://localhost:4318/v1/traces``
    with zero extra configuration. Supports JSON and Protobuf.
    """
    try:
        content_type = request.headers.get("content-type", "")
        content_encoding = request.headers.get("content-encoding", "")

        raw_data = await request.body()
        if "gzip" in content_encoding:
            import gzip
            raw_data = gzip.decompress(raw_data)

        if "application/x-protobuf" in content_type:
            pb_data = TracesData.FromString(raw_data)
            body = MessageToDict(pb_data)
        else:
            import json
            body = json.loads(raw_data)

        spans = parse_otlp_payload(body)

        if spans:
            trace_store.add_spans(spans)
            logger.debug("Ingested %d spans across traces", len(spans))

        return JSONResponse(
            content={"accepted_spans": len(spans)},
            status_code=200,
        )
    except Exception as exc:
        logger.error("Failed to process /v1/traces request: %s", exc, exc_info=True)
        return JSONResponse(
            content={"error": str(exc)},
            status_code=400,
        )


@app.get("/traces")
async def list_traces() -> list[dict[str, Any]]:
    """Return a summary of all stored traces.

    Each entry contains trace_id, span_count, and the name of the root
    span (the span with no parent_span_id). If no root is found, the
    root_span_name falls back to the first span's name.
    """
    summaries: list[dict[str, Any]] = []

    for trace_id, spans in trace_store.all_traces():
        # Find the root span (no parent).
        root_span = next(
            (s for s in spans if s.parent_span_id is None),
            None,
        )
        root_name = root_span.name if root_span else spans[0].name

        summaries.append({
            "trace_id": trace_id,
            "span_count": len(spans),
            "root_span_name": root_name,
        })

    return summaries


@app.get("/traces/{trace_id}")
async def get_trace_tree(trace_id: str) -> dict[str, Any]:
    """Return the full span tree for a single trace.

    Uses build_tree() to reconstruct the parent-child hierarchy from
    the flat span list, then serializes via dataclasses.asdict.
    """
    spans = trace_store.get_trace(trace_id)
    if spans is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    roots = build_tree(spans)

    def _serialize_node(node: TreeNode) -> dict[str, Any]:
        """Recursively convert a TreeNode to a JSON-safe dict."""
        span_dict = asdict(node.span)
        span_dict["duration_ms"] = node.span.duration_ms
        return {
            "span": span_dict,
            "children": [_serialize_node(child) for child in node.children],
        }

    return {
        "trace_id": trace_id,
        "span_count": len(spans),
        "tree": [_serialize_node(root) for root in roots],
    }
