"""Send a realistic fake checkout trace to the Sonar OTLP ingestion endpoint.

This script constructs a 5-span trace matching the real OTLP/HTTP JSON
shape and POSTs it to http://localhost:4318/v1/traces.

Trace shape:
  api-gateway  POST /checkout                          812ms  OK
  ├── inventory-service  CheckStock           [grpc]    94ms  OK
  ├── billing-service    ChargeCard           [grpc]   690ms  ERROR
  │   └── ledger-db      QueryBalance         [http]    12ms  OK
  └── order-events       PublishOrderCreated  [kafka]    3ms  OK

Usage:
    python scripts/send_fake_span.py
"""

import httpx
import time
import uuid


def _nano(ms_offset: int, base: int) -> str:
    """Return a nanosecond timestamp string offset by `ms_offset` ms."""
    return str(base + ms_offset * 1_000_000)


def build_checkout_trace() -> dict:
    """Build a 5-span OTLP JSON payload for a checkout trace."""

    trace_id = uuid.uuid4().hex
    base_ns = time.time_ns()

    # Span IDs (8-byte hex)
    gateway_id = uuid.uuid4().hex[:16]
    inventory_id = uuid.uuid4().hex[:16]
    billing_id = uuid.uuid4().hex[:16]
    ledger_id = uuid.uuid4().hex[:16]
    kafka_id = uuid.uuid4().hex[:16]

    return {
        "resourceSpans": [
            # ── api-gateway service ──────────────────────────
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "api-gateway"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "opentelemetry-java",
                            "version": "1.32.0",
                        },
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": gateway_id,
                                "parentSpanId": "",
                                "name": "POST /checkout",
                                "kind": 2,  # SERVER
                                "startTimeUnixNano": _nano(0, base_ns),
                                "endTimeUnixNano": _nano(812, base_ns),
                                "status": {"code": 1},  # OK
                                "attributes": [
                                    {
                                        "key": "http.method",
                                        "value": {"stringValue": "POST"},
                                    },
                                    {
                                        "key": "http.route",
                                        "value": {
                                            "stringValue": "/checkout"
                                        },
                                    },
                                    {
                                        "key": "http.status_code",
                                        "value": {"intValue": "500"},
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            # ── inventory-service ────────────────────────────
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "inventory-service"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "opentelemetry-java",
                            "version": "1.32.0",
                        },
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": inventory_id,
                                "parentSpanId": gateway_id,
                                "name": "CheckStock",
                                "kind": 3,  # CLIENT
                                "startTimeUnixNano": _nano(5, base_ns),
                                "endTimeUnixNano": _nano(99, base_ns),
                                "status": {"code": 1},
                                "attributes": [
                                    {
                                        "key": "rpc.system",
                                        "value": {"stringValue": "grpc"},
                                    },
                                    {
                                        "key": "rpc.service",
                                        "value": {
                                            "stringValue": "InventoryService"
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            # ── billing-service (ERROR) ──────────────────────
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "billing-service"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "opentelemetry-java",
                            "version": "1.32.0",
                        },
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": billing_id,
                                "parentSpanId": gateway_id,
                                "name": "ChargeCard",
                                "kind": 3,
                                "startTimeUnixNano": _nano(100, base_ns),
                                "endTimeUnixNano": _nano(790, base_ns),
                                "status": {
                                    "code": 2,  # ERROR
                                    "message": "Payment declined: insufficient funds",
                                },
                                "attributes": [
                                    {
                                        "key": "rpc.system",
                                        "value": {"stringValue": "grpc"},
                                    },
                                    {
                                        "key": "rpc.grpc.status_code",
                                        "value": {"intValue": "13"},
                                    },
                                    {
                                        "key": "error.message",
                                        "value": {
                                            "stringValue": "Payment declined: insufficient funds"
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            # ── ledger-db (child of billing) ─────────────────
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "ledger-db"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "opentelemetry-java",
                            "version": "1.32.0",
                        },
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": ledger_id,
                                "parentSpanId": billing_id,
                                "name": "QueryBalance",
                                "kind": 3,
                                "startTimeUnixNano": _nano(105, base_ns),
                                "endTimeUnixNano": _nano(117, base_ns),
                                "status": {"code": 1},
                                "attributes": [
                                    {
                                        "key": "db.system",
                                        "value": {"stringValue": "postgresql"},
                                    },
                                    {
                                        "key": "db.statement",
                                        "value": {
                                            "stringValue": "SELECT balance FROM accounts WHERE user_id = $1"
                                        },
                                    },
                                    {
                                        "key": "db.name",
                                        "value": {
                                            "stringValue": "ledger"
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            # ── order-events (kafka) ─────────────────────────
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "order-events"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "opentelemetry-java",
                            "version": "1.32.0",
                        },
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": kafka_id,
                                "parentSpanId": gateway_id,
                                "name": "PublishOrderCreated",
                                "kind": 4,  # PRODUCER
                                "startTimeUnixNano": _nano(795, base_ns),
                                "endTimeUnixNano": _nano(798, base_ns),
                                "status": {"code": 1},
                                "attributes": [
                                    {
                                        "key": "messaging.system",
                                        "value": {"stringValue": "kafka"},
                                    },
                                    {
                                        "key": "messaging.destination.name",
                                        "value": {
                                            "stringValue": "order.created"
                                        },
                                    },
                                    {
                                        "key": "messaging.kafka.partition",
                                        "value": {"intValue": "3"},
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
        ]
    }


def main():
    """Build and send the fake trace, then print the result."""
    payload = build_checkout_trace()

    print("Sending fake checkout trace to http://localhost:4318/v1/traces ...")

    response = httpx.post(
        "http://localhost:4318/v1/traces",
        json=payload,
        timeout=5.0,
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    # Also fetch the summary to verify it landed.
    print("\nFetching trace summary from GET /traces ...")
    summary = httpx.get("http://localhost:4318/traces", timeout=5.0)
    print(f"Traces stored: {summary.json()}")


if __name__ == "__main__":
    main()
