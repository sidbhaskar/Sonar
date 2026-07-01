"""Quick verification: dump all stored spans to confirm parsing."""

import httpx
import json
from dataclasses import asdict

# Import directly — this starts a fresh Python process that imports
# the server module, so we can't see the running server's in-memory data.
# Instead we'll add a temporary debug route via the API.

def main():
    base = "http://localhost:4318"

    # 1. Get trace summary
    traces = httpx.get(f"{base}/traces", timeout=5).json()
    print(f"=== {len(traces)} trace(s) stored ===\n")

    for t in traces:
        print(f"  Trace {t['trace_id'][:12]}...  "
              f"{t['span_count']} spans  "
              f"root=\"{t['root_span_name']}\"")

    # 2. POST a fresh trace and immediately query it back via /v1/traces
    #    to verify round-trip parsing
    print("\n=== Round-trip test: send + query ===\n")
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from send_fake_span import build_checkout_trace  # type: ignore
    payload = build_checkout_trace()

    # Count spans in the payload we're about to send
    expected = sum(
        len(span_list)
        for rs in payload["resourceSpans"]
        for ss in rs["scopeSpans"]
        for span_list in [ss["spans"]]
    )
    print(f"Payload contains {expected} spans")

    resp = httpx.post(f"{base}/v1/traces", json=payload, timeout=5)
    result = resp.json()
    print(f"POST /v1/traces -> {resp.status_code}, accepted: {result['accepted_spans']}")
    assert result["accepted_spans"] == expected, "Span count mismatch!"

    # 3. Re-fetch and find our new trace
    traces_after = httpx.get(f"{base}/traces", timeout=5).json()
    print(f"\nTotal traces after: {len(traces_after)}")

    # Find the newest trace (last in list)
    newest = traces_after[-1]
    print(f"Newest trace: {newest['trace_id'][:12]}... "
          f"spans={newest['span_count']} root=\"{newest['root_span_name']}\"")

    assert newest["span_count"] == 5, f"Expected 5 spans, got {newest['span_count']}"
    assert newest["root_span_name"] == "POST /checkout"

    print("\n[OK] All pipeline checks passed!")


if __name__ == "__main__":
    main()
