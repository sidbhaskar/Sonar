# Build All Remaining Sonar Features

Implement all 10 gaps identified in the analysis, working through them in dependency order (foundational fixes first, then features, then packaging).

## Proposed Changes

### Phase 1: Foundational Fixes (must-fix before adding features)

---

#### 1. Thread-Safe Trace Store

Replace the raw `dict` with a dedicated `TraceStore` class that uses `threading.Lock` internally. All reads and writes go through this class.

##### [NEW] [store.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ingestion/store.py)
- `TraceStore` class wrapping a dict with a `threading.Lock`
- Methods: `add_spans()`, `get_trace()`, `all_traces()`, `trace_ids()`, `__len__()`
- Built-in **eviction** (max 500 traces, FIFO) — this covers item #4 from the analysis too

##### [MODIFY] [server.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ingestion/server.py)
- Replace `trace_store: dict` with `TraceStore` instance
- Update `ingest_traces()`, `list_traces()`, `get_trace_tree()` to use new API

##### [MODIFY] [app.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ui/app.py)
- Import `TraceStore` instead of raw dict
- Update polling and rendering to use `TraceStore` methods

---

#### 2. Error Handling & Logging in Ingestion

##### [MODIFY] [server.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ingestion/server.py)
- Add `logging.getLogger(__name__)` throughout
- Wrap `parse_otlp_payload()` in try/except — return 400 with error message on malformed input
- Add field validation (missing `traceId`, `spanId` → logged warning, span skipped)
- Log successful ingestion at DEBUG level

---

#### 3. Trace Duration Fix

##### [MODIFY] [app.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ui/app.py)
- In `TraceListItem`, compute total trace duration as `max(end_time) - min(start_time)` across all spans instead of using `root.duration_ms`

---

### Phase 2: New Features

---

#### 4. OTLP gRPC Ingestion (Port 4317)

##### [NEW] [grpc_server.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ingestion/grpc_server.py)
- gRPC server using `grpcio` listening on port 4317
- Implements `opentelemetry.proto.collector.trace.v1.TraceService/Export`
- Converts protobuf messages to the same JSON-like dict format, then calls `parse_otlp_payload()` to reuse existing parsing
- Runs in its own daemon thread (like the HTTP server)

##### [MODIFY] [main.py](file:///d:/AntiGravity_Projects/Sonar/sonar/main.py)
- Start gRPC server thread alongside the HTTP server thread
- Update top bar to show both ports

##### [MODIFY] [app.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ui/app.py)
- Update top bar to show `http:4318 · grpc:4317`

> [!NOTE]
> This requires adding `grpcio` and `opentelemetry-proto` to dependencies. The project already imports `opentelemetry.proto` in server.py for protobuf parsing, so `opentelemetry-proto` is already an implicit dependency.

---

#### 5. Inspector Panel Toggle (responsive collapse)

##### [MODIFY] [app.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ui/app.py)
- Add `i` keybinding to toggle inspector panel visibility
- On narrow terminals (< 100 cols), auto-hide inspector on mount
- Toggle changes `display` of `#inspector-panel`

---

### Phase 3: Test Coverage

---

#### 6. Comprehensive Tests

##### [NEW] [test_models.py](file:///d:/AntiGravity_Projects/Sonar/sonar/tests/test_models.py)
- `Span.duration_ms` calculation

##### [NEW] [test_server.py](file:///d:/AntiGravity_Projects/Sonar/sonar/tests/test_server.py)
- `parse_otlp_payload()` — valid payload, empty payload, missing fields, multiple resource spans
- `_extract_attribute_value()` — all OTLP value types (string, int, bool, double, array)
- `_parse_status()` — code 0/1/2, string variants, None
- `_normalize_id()` — hex passthrough, base64 decode, empty string

##### [NEW] [test_store.py](file:///d:/AntiGravity_Projects/Sonar/sonar/tests/test_store.py)
- Thread safety (concurrent add + read)
- Eviction policy (add > max, oldest dropped)
- Basic CRUD operations

##### [NEW] [test_helpers.py](file:///d:/AntiGravity_Projects/Sonar/sonar/tests/test_helpers.py)
- `detect_protocol()` — HTTP, gRPC, Kafka, unknown
- `format_span_label()` — normal span, errored span, descendant error propagation
- `has_error()` / `_subtree_has_error()`

##### [NEW] [test_integration.py](file:///d:/AntiGravity_Projects/Sonar/sonar/tests/test_integration.py)
- Full HTTP round-trip using `httpx.AsyncClient` + FastAPI TestClient
- Send OTLP payload → verify `/traces` summary → verify `/traces/{id}` tree structure

---

### Phase 4: Packaging & Polish

---

#### 7. Project Packaging

##### [NEW] [pyproject.toml](file:///d:/AntiGravity_Projects/Sonar/pyproject.toml)
- Package metadata (name, version, description, author)
- Dependencies from `requirements.txt`
- CLI entry point: `sonar = sonar.main:main`
- Dev dependencies: `pytest`, `httpx`

##### [MODIFY] [\_\_init\_\_.py files](file:///d:/AntiGravity_Projects/Sonar/sonar)
- Add `__all__` exports to `core/__init__.py`, `ingestion/__init__.py`, `ui/__init__.py`

---

## Execution Order

I'll work through these in this exact order:
1. `TraceStore` class (thread safety + eviction)
2. Wire `TraceStore` into server + UI
3. Error handling & logging in ingestion
4. Trace duration fix
5. gRPC ingestion server
6. Inspector panel toggle
7. All test files
8. `pyproject.toml` + `__init__.py` exports
9. Run all tests to verify

## Verification Plan

### Automated Tests
```bash
python -m pytest sonar/tests/ -v
```

### Manual Verification
- Run `python -m sonar.main` and send fake spans with `python scripts/send_fake_span.py`
- Verify traces appear in the TUI, inspector works, error filtering works
