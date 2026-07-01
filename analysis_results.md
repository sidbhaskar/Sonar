# Sonar — Project Completeness Analysis

## What's Built ✅

| Component | File(s) | Status |
|---|---|---|
| **Data Model** | [models.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ingestion/models.py) | `Span` dataclass with all core fields + `duration_ms` property |
| **OTLP Ingestion Server** | [server.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ingestion/server.py) | FastAPI on port 4318, accepts JSON + Protobuf + gzip, parses OTLP payload |
| **Tree Builder** | [tree_builder.py](file:///d:/AntiGravity_Projects/Sonar/sonar/core/tree_builder.py) | Builds parent-child hierarchy, handles orphan spans |
| **TUI App** | [app.py](file:///d:/AntiGravity_Projects/Sonar/sonar/ui/app.py) | 3-pane layout, trace list, span tree, inspector, search, error filter |
| **Main Entry Point** | [main.py](file:///d:/AntiGravity_Projects/Sonar/sonar/main.py) | Runs FastAPI in daemon thread + Textual on main thread |
| **Test Scripts** | [send_fake_span.py](file:///d:/AntiGravity_Projects/Sonar/scripts/send_fake_span.py), [verify_pipeline.py](file:///d:/AntiGravity_Projects/Sonar/scripts/verify_pipeline.py) | Realistic 5-span checkout trace generator + round-trip verification |
| **Unit Tests** | [test_tree_builder.py](file:///d:/AntiGravity_Projects/Sonar/sonar/tests/test_tree_builder.py) | 10 tests covering tree building (empty, single, multi-level, orphan, order-independent) |

---

## What's Remaining to Build 🔧

### 1. **OTLP gRPC Ingestion** (Core Feature Gap)

> [!IMPORTANT]
> The project description lists **OTLP gRPC ingestion** as a core feature, but only HTTP is implemented. Real OTel agents commonly export over gRPC (port 4317), not just HTTP (port 4318). Without this, services configured with the default gRPC exporter won't connect.

**Work needed:**
- Add a gRPC server (using `grpcio`) listening on port **4317**
- Accept `opentelemetry.proto.collector.trace.v1.ExportTraceServiceRequest` messages
- Route parsed spans into the same `trace_store`

---

### 2. **Trace Duration Calculation** (Data Bug)

The trace list shows `root.duration_ms` as the total trace duration, but the **actual trace duration** should be `max(span.end_time) - min(span.start_time)` across all spans in the trace. A child span could end after the root if clocks are skewed or spans arrive from different services. This is a logic gap, not a UI issue.

---

### 3. **Thread Safety for `trace_store`** (Correctness Issue)

> [!WARNING]
> `trace_store` is a plain `dict` shared between the FastAPI thread (writes) and the Textual main thread (reads via polling). There is **no locking**. This is a data race — concurrent dict mutation + iteration can cause `RuntimeError: dictionary changed size during iteration`.

**Work needed:**
- Wrap `trace_store` in a `threading.Lock`, or
- Use a thread-safe data structure (e.g., a class with lock-guarded methods)

---

### 4. **Trace Store Limits / Eviction** (Memory Management)

The in-memory store grows unbounded — there is no eviction policy. In a long dev session with many requests, memory will grow indefinitely.

**Work needed:**
- Add a max trace count (e.g., keep last 500 traces)
- Evict oldest traces on overflow (LRU or FIFO)

---

### 5. **Missing Test Coverage**

| Area | Current Coverage | Missing |
|---|---|---|
| `tree_builder` | ✅ 10 tests | Covered well |
| `parse_otlp_payload()` | ❌ None | Parsing logic, edge cases (empty payloads, malformed spans, base64 IDs, missing fields) |
| `_extract_attribute_value()` | ❌ None | All OTLP value types (arrays, nested kvlists, booleans) |
| `_parse_status()` | ❌ None | Status code edge cases (string vs int, UNSET) |
| `_normalize_id()` | ❌ None | Base64-to-hex conversion, empty strings, hex passthrough |
| `detect_protocol()` | ❌ None | Protocol detection from span attributes |
| `format_span_label()` | ❌ None | Label generation with error markers, protocol badges |
| Integration test (HTTP round-trip) | ❌ None | Only manual script exists, no pytest-based integration test |

---

### 6. **No `setup.py` / `pyproject.toml`** (Packaging)

The project has no Python packaging configuration. There are two `requirements.txt` files (root and `sonar/`) but no installable package definition. This means:
- Can't `pip install -e .` for development
- No CLI entry point (must run `python -m sonar.main` manually)
- Can't distribute as a single installable tool

**Work needed:**
- Add `pyproject.toml` with entry point: `sonar = sonar.main:main`

---

### 7. **No OTLP gRPC Proto Compilation Pipeline**

The project imports `opentelemetry.proto.trace.v1.trace_pb2` directly (likely from the `opentelemetry-proto` pip package), but there's no documented setup for proto compilation or a note on which package provides this. This could be a setup friction point for contributors.

---

### 8. **No Error Handling / Resilience in Ingestion**

- No try/except around payload parsing — a malformed span payload will crash the endpoint with an unhandled 500
- No validation on required fields (what if `traceId` is missing entirely?)
- No logging at all in the ingestion path (the uvicorn log level is set to `error`, and there's no application-level logger)

**Work needed:**
- Add structured logging (at least `logging.getLogger(__name__)`)
- Wrap `parse_otlp_payload` calls in try/except with logged warnings
- Return proper OTLP error responses on malformed input

---

### 9. **Responsive Inspector Panel Collapse** (Functional Behavior)

> [!NOTE]
> The design spec (Section 2) calls for the inspector panel to **collapse at narrow terminal widths** (~80 cols) and be togglable with `i`. This is not a UI refinement — it's a missing functional behavior (keyboard binding + layout toggle logic).

---

### 10. **Missing `__init__.py` Exports**

The `__init__.py` files in `core/`, `ingestion/`, and `ui/` are essentially empty (just module docstrings). While this works, explicit `__all__` exports would be cleaner for the public API.

---

## Priority Summary

| Priority | Item | Effort |
|---|---|---|
| 🔴 High | Thread safety for `trace_store` | Small |
| 🔴 High | Error handling in ingestion | Medium |
| 🟠 Medium | OTLP gRPC support (port 4317) | Medium-Large |
| 🟠 Medium | Test coverage for parsing/ingestion | Medium |
| 🟠 Medium | Trace store eviction policy | Small |
| 🟡 Low | Trace duration calculation fix | Small |
| 🟡 Low | `pyproject.toml` + CLI entry point | Small |
| 🟡 Low | Inspector panel collapse at narrow widths | Small |
| ⚪ Nice-to-have | Logging infrastructure | Small |
| ⚪ Nice-to-have | Proto compilation docs | Trivial |
