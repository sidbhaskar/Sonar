"""Send multiple realistic fake traces to the Sonar OTLP ingestion endpoint.

Traces sent:
  1. Checkout flow   (5 spans, 1 ERROR — payment declined)
  2. Login flow      (4 spans, all OK)
  3. Search flow     (3 spans, all OK)
  4. Order pipeline  (6 spans, 1 ERROR — timeout)
  5. Notification    (3 spans, all OK)

Usage:
    python scripts/send_fake_span.py
"""

import httpx
import time
import uuid


def _nano(ms_offset: int, base: int) -> str:
    return str(base + ms_offset * 1_000_000)


def _span(trace_id, span_id, parent_id, name, kind, start_ms, end_ms,
          status_code=1, status_msg="", attributes=None, svc="unknown"):
    attrs = []
    for k, v in (attributes or {}).items():
        if isinstance(v, int):
            attrs.append({"key": k, "value": {"intValue": str(v)}})
        else:
            attrs.append({"key": k, "value": {"stringValue": str(v)}})
    return {
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": svc}},
        ]},
        "scopeSpans": [{
            "scope": {"name": "opentelemetry-python", "version": "1.0.0"},
            "spans": [{
                "traceId": trace_id,
                "spanId": span_id,
                "parentSpanId": parent_id,
                "name": name,
                "kind": kind,
                "startTimeUnixNano": _nano(start_ms, base),
                "endTimeUnixNano": _nano(end_ms, base),
                "status": {"code": status_code, "message": status_msg} if status_msg else {"code": status_code},
                "attributes": attrs,
            }],
        }],
    }


base = time.time_ns()


# ── Trace 1: Checkout (ERROR) ────────────────────────────
def build_checkout_trace():
    tid = uuid.uuid4().hex
    gw = uuid.uuid4().hex[:16]
    inv = uuid.uuid4().hex[:16]
    bill = uuid.uuid4().hex[:16]
    led = uuid.uuid4().hex[:16]
    mq = uuid.uuid4().hex[:16]
    return [
        _span(tid, gw, "", "POST /checkout", 2, 0, 812, 1, svc="api-gateway",
              attributes={"http.method": "POST", "http.route": "/checkout", "http.status_code": 500}),
        _span(tid, inv, gw, "CheckStock", 3, 5, 99, 1, svc="inventory-service",
              attributes={"rpc.system": "grpc", "rpc.service": "InventoryService"}),
        _span(tid, bill, gw, "ChargeCard", 3, 100, 790, 2,
              "Payment declined: insufficient funds", svc="billing-service",
              attributes={"rpc.system": "grpc", "rpc.grpc.status_code": 13,
                          "error.message": "Payment declined: insufficient funds"}),
        _span(tid, led, bill, "QueryBalance", 3, 105, 117, 1, svc="ledger-db",
              attributes={"db.system": "postgresql", "db.statement": "SELECT balance FROM accounts WHERE user_id = $1",
                          "db.name": "ledger"}),
        _span(tid, mq, gw, "PublishOrderCreated", 4, 795, 798, 1, svc="order-events",
              attributes={"messaging.system": "kafka", "messaging.destination.name": "order.created",
                          "messaging.kafka.partition": 3}),
    ]


# ── Trace 2: Login (OK) ─────────────────────────────────
def build_login_trace():
    tid = uuid.uuid4().hex
    gw = uuid.uuid4().hex[:16]
    auth = uuid.uuid4().hex[:16]
    sess = uuid.uuid4().hex[:16]
    token = uuid.uuid4().hex[:16]
    return [
        _span(tid, gw, "", "POST /api/login", 2, 0, 245, 1, svc="api-gateway",
              attributes={"http.method": "POST", "http.route": "/api/login", "http.status_code": 200}),
        _span(tid, auth, gw, "AuthenticateUser", 3, 10, 180, 1, svc="auth-service",
              attributes={"rpc.system": "grpc", "rpc.service": "AuthService"}),
        _span(tid, sess, auth, "CreateSession", 3, 185, 210, 1, svc="session-store",
              attributes={"db.system": "redis", "db.statement": "SET session:* TTL 3600"}),
        _span(tid, token, auth, "GenerateJWT", 3, 215, 240, 1, svc="auth-service",
              attributes={"auth.method": "jwt", "auth.token.ttl": 3600}),
    ]


# ── Trace 3: Search (OK) ─────────────────────────────────
def build_search_trace():
    tid = uuid.uuid4().hex
    gw = uuid.uuid4().hex[:16]
    search = uuid.uuid4().hex[:16]
    cache = uuid.uuid4().hex[:16]
    return [
        _span(tid, gw, "", "GET /api/search", 2, 0, 156, 1, svc="api-gateway",
              attributes={"http.method": "GET", "http.route": "/api/search", "http.status_code": 200}),
        _span(tid, search, gw, "QueryElasticsearch", 3, 8, 120, 1, svc="search-service",
              attributes={"db.system": "elasticsearch", "db.statement": '{"query":{"match":{"title":"laptop"}}}',
                          "db.name": "products"}),
        _span(tid, cache, search, "CheckCache", 3, 125, 145, 1, svc="cache-layer",
              attributes={"db.system": "redis", "db.statement": "GET search:query:*"}),
    ]


# ── Trace 4: Order pipeline (deep chain, 1 ERROR) ────────
def build_order_pipeline_trace():
    tid = uuid.uuid4().hex
    api = uuid.uuid4().hex[:16]
    validate = uuid.uuid4().hex[:16]
    inventory = uuid.uuid4().hex[:16]
    reserve = uuid.uuid4().hex[:16]
    payment = uuid.uuid4().hex[:16]
    notify = uuid.uuid4().hex[:16]
    return [
        _span(tid, api, "", "POST /api/orders", 2, 0, 1200, 1, svc="api-gateway",
              attributes={"http.method": "POST", "http.route": "/api/orders", "http.status_code": 504}),
        _span(tid, validate, api, "ValidateOrder", 3, 5, 45, 1, svc="order-service",
              attributes={"rpc.system": "grpc", "rpc.service": "OrderService"}),
        _span(tid, inventory, validate, "ReserveStock", 3, 50, 320, 1, svc="inventory-service",
              attributes={"rpc.system": "grpc", "rpc.service": "InventoryService"}),
        _span(tid, reserve, inventory, "LockItem", 3, 55, 80, 1, svc="inventory-service",
              attributes={"db.system": "postgresql", "db.statement": "UPDATE stock SET reserved = true WHERE sku = $1"}),
        _span(tid, payment, validate, "ProcessPayment", 3, 330, 1150, 2,
              "Connection to payment gateway timed out after 800ms", svc="payment-service",
              attributes={"rpc.system": "grpc", "rpc.grpc.status_code": 14,
                          "error.type": "DEADLINE_EXCEEDED",
                          "error.message": "Connection to payment gateway timed out after 800ms"}),
        _span(tid, notify, validate, "SendOrderConfirmation", 4, 1160, 1190, 1, svc="notification-service",
              attributes={"messaging.system": "kafka", "messaging.destination.name": "notifications"}),
    ]


# ── Trace 5: Notification (OK) ──────────────────────────
def build_notification_trace():
    tid = uuid.uuid4().hex
    gw = uuid.uuid4().hex[:16]
    email = uuid.uuid4().hex[:16]
    sms = uuid.uuid4().hex[:16]
    return [
        _span(tid, gw, "", "POST /api/notify", 2, 0, 310, 1, svc="api-gateway",
              attributes={"http.method": "POST", "http.route": "/api/notify", "http.status_code": 200}),
        _span(tid, email, gw, "SendEmail", 3, 10, 200, 1, svc="email-service",
              attributes={"messaging.system": "kafka", "messaging.destination.name": "email.send",
                          "email.to": "user@example.com", "email.subject": "Your order is ready"}),
        _span(tid, sms, gw, "SendSMS", 3, 15, 280, 1, svc="sms-service",
              attributes={"messaging.system": "kafka", "messaging.destination.name": "sms.send",
                          "sms.to": "+1234567890"}),
    ]


ALL_TRACES = [
    ("checkout", build_checkout_trace),
    ("login", build_login_trace),
    ("search", build_search_trace),
    ("order-pipeline", build_order_pipeline_trace),
    ("notification", build_notification_trace),
]


def main():
    print(f"Sending {len(ALL_TRACES)} fake traces to http://localhost:4318/v1/traces ...\n")

    for name, builder in ALL_TRACES:
        spans = builder()
        payload = {"resourceSpans": spans}
        resp = httpx.post("http://localhost:4318/v1/traces", json=payload, timeout=5.0)
        span_count = sum(len(s["scopeSpans"][0]["spans"]) for s in payload["resourceSpans"])
        status = "OK" if resp.status_code == 200 else f"FAIL({resp.status_code})"
        print(f"  [{status}] {name:20s} — {span_count} spans")

    print("\nFetching trace summary from GET /traces ...")
    summary = httpx.get("http://localhost:4318/traces", timeout=5.0)
    print(f"Traces stored: {summary.json()}")


if __name__ == "__main__":
    main()
