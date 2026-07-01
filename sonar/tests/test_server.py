"""Tests for OTLP parsing and server helpers in sonar.ingestion.server."""

import pytest

from sonar.ingestion.server import (
    _extract_attribute_value,
    _parse_attributes,
    _extract_service_name,
    _parse_status,
    _normalize_id,
    parse_otlp_payload,
)


# ---------------------------------------------------------------------------
# _extract_attribute_value
# ---------------------------------------------------------------------------

class TestExtractAttributeValue:
    """Unwrap OTLP AnyValue wrappers to plain Python values."""

    def test_string_value(self):
        assert _extract_attribute_value({"stringValue": "hello"}) == "hello"

    def test_int_value(self):
        assert _extract_attribute_value({"intValue": "42"}) == 42

    def test_int_value_as_int(self):
        assert _extract_attribute_value({"intValue": 42}) == 42

    def test_bool_value_true(self):
        assert _extract_attribute_value({"boolValue": True}) is True

    def test_bool_value_false(self):
        assert _extract_attribute_value({"boolValue": False}) is False

    def test_double_value(self):
        assert _extract_attribute_value({"doubleValue": 3.14}) == 3.14

    def test_array_value(self):
        result = _extract_attribute_value({
            "arrayValue": {
                "values": [
                    {"stringValue": "a"},
                    {"intValue": "1"},
                ]
            }
        })
        assert result == ["a", 1]

    def test_array_value_empty(self):
        result = _extract_attribute_value({"arrayValue": {}})
        assert result == []

    def test_unknown_type_returns_raw_dict(self):
        raw = {"kvlistValue": {"values": []}}
        result = _extract_attribute_value(raw)
        assert result == raw


# ---------------------------------------------------------------------------
# _parse_attributes
# ---------------------------------------------------------------------------

class TestParseAttributes:
    """Convert OTLP attributes array to flat dict."""

    def test_basic(self):
        attrs = [
            {"key": "http.method", "value": {"stringValue": "GET"}},
            {"key": "http.status_code", "value": {"intValue": "200"}},
        ]
        result = _parse_attributes(attrs)
        assert result == {"http.method": "GET", "http.status_code": 200}

    def test_empty_list(self):
        assert _parse_attributes([]) == {}

    def test_missing_key_skipped(self):
        attrs = [{"value": {"stringValue": "orphan"}}]
        assert _parse_attributes(attrs) == {}

    def test_missing_value_skipped(self):
        attrs = [{"key": "orphan"}]
        assert _parse_attributes(attrs) == {}


# ---------------------------------------------------------------------------
# _extract_service_name
# ---------------------------------------------------------------------------

class TestExtractServiceName:
    """Pull service.name from OTLP resource block."""

    def test_found(self):
        resource = {
            "attributes": [
                {"key": "service.name", "value": {"stringValue": "my-svc"}}
            ]
        }
        assert _extract_service_name(resource) == "my-svc"

    def test_missing_attributes(self):
        assert _extract_service_name({}) == "unknown"

    def test_no_service_name_key(self):
        resource = {
            "attributes": [
                {"key": "host.name", "value": {"stringValue": "server-1"}}
            ]
        }
        assert _extract_service_name(resource) == "unknown"


# ---------------------------------------------------------------------------
# _parse_status
# ---------------------------------------------------------------------------

class TestParseStatus:
    """Map OTLP status object to 'OK' or 'ERROR'."""

    def test_none_is_ok(self):
        assert _parse_status(None) == "OK"

    def test_code_0_unset_is_ok(self):
        assert _parse_status({"code": 0}) == "OK"

    def test_code_1_ok(self):
        assert _parse_status({"code": 1}) == "OK"

    def test_code_2_error(self):
        assert _parse_status({"code": 2}) == "ERROR"

    def test_code_string_2_error(self):
        assert _parse_status({"code": "2"}) == "ERROR"

    def test_code_string_enum_error(self):
        assert _parse_status({"code": "STATUS_CODE_ERROR"}) == "ERROR"

    def test_empty_dict_is_ok(self):
        assert _parse_status({}) == "OK"

    def test_missing_code_key_is_ok(self):
        assert _parse_status({"message": "something"}) == "OK"


# ---------------------------------------------------------------------------
# _normalize_id
# ---------------------------------------------------------------------------

class TestNormalizeId:
    """Normalize base64 or hex IDs to hex strings."""

    def test_empty_string(self):
        assert _normalize_id("") == ""

    def test_hex_16_char_passthrough(self):
        """16-char hex (8-byte span ID) passes through unchanged."""
        assert _normalize_id("abcdef0123456789") == "abcdef0123456789"

    def test_hex_32_char_passthrough(self):
        """32-char hex (16-byte trace ID) passes through unchanged."""
        hex_id = "a" * 32
        assert _normalize_id(hex_id) == hex_id

    def test_base64_decoded(self):
        """Non-standard-length IDs are treated as base64."""
        import base64
        raw_bytes = bytes.fromhex("abcdef0123456789")
        b64 = base64.b64encode(raw_bytes).decode()
        result = _normalize_id(b64)
        assert result == "abcdef0123456789"


# ---------------------------------------------------------------------------
# parse_otlp_payload
# ---------------------------------------------------------------------------

class TestParseOtlpPayload:
    """Full OTLP payload parsing."""

    def _minimal_payload(self, **span_overrides) -> dict:
        """Build a minimal valid OTLP JSON payload with one span."""
        span = {
            "traceId": "a" * 32,
            "spanId": "b" * 16,
            "parentSpanId": "",
            "name": "test-span",
            "startTimeUnixNano": "1000000",
            "endTimeUnixNano": "2000000",
            "status": {"code": 1},
            "attributes": [],
        }
        span.update(span_overrides)
        return {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "test-svc"}}
                    ]
                },
                "scopeSpans": [{
                    "scope": {"name": "test"},
                    "spans": [span],
                }],
            }]
        }

    def test_single_span(self):
        spans = parse_otlp_payload(self._minimal_payload())
        assert len(spans) == 1
        s = spans[0]
        assert s.name == "test-span"
        assert s.service_name == "test-svc"
        assert s.trace_id == "a" * 32
        assert s.span_id == "b" * 16
        assert s.parent_span_id is None  # Empty string normalised to None.
        assert s.status == "OK"

    def test_empty_payload(self):
        assert parse_otlp_payload({}) == []
        assert parse_otlp_payload({"resourceSpans": []}) == []

    def test_error_status(self):
        spans = parse_otlp_payload(
            self._minimal_payload(status={"code": 2, "message": "fail"})
        )
        assert spans[0].status == "ERROR"

    def test_attributes_parsed(self):
        attrs = [
            {"key": "http.method", "value": {"stringValue": "POST"}},
            {"key": "http.status_code", "value": {"intValue": "500"}},
        ]
        spans = parse_otlp_payload(self._minimal_payload(attributes=attrs))
        assert spans[0].attributes == {"http.method": "POST", "http.status_code": 500}

    def test_missing_trace_id_skipped(self):
        """Spans with empty traceId are skipped, not crash."""
        spans = parse_otlp_payload(self._minimal_payload(traceId=""))
        assert len(spans) == 0

    def test_missing_span_id_skipped(self):
        """Spans with empty spanId are skipped, not crash."""
        spans = parse_otlp_payload(self._minimal_payload(spanId=""))
        assert len(spans) == 0

    def test_parent_span_id_normalized(self):
        parent_id = "c" * 16
        spans = parse_otlp_payload(
            self._minimal_payload(parentSpanId=parent_id)
        )
        assert spans[0].parent_span_id == parent_id

    def test_multiple_resource_spans(self):
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "svc-a"}}
                        ]
                    },
                    "scopeSpans": [{
                        "scope": {"name": "test"},
                        "spans": [{
                            "traceId": "a" * 32,
                            "spanId": "1" * 16,
                            "parentSpanId": "",
                            "name": "span-a",
                            "startTimeUnixNano": "0",
                            "endTimeUnixNano": "1000000",
                            "attributes": [],
                        }],
                    }],
                },
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "svc-b"}}
                        ]
                    },
                    "scopeSpans": [{
                        "scope": {"name": "test"},
                        "spans": [{
                            "traceId": "a" * 32,
                            "spanId": "2" * 16,
                            "parentSpanId": "1" * 16,
                            "name": "span-b",
                            "startTimeUnixNano": "0",
                            "endTimeUnixNano": "500000",
                            "attributes": [],
                        }],
                    }],
                },
            ]
        }
        spans = parse_otlp_payload(payload)
        assert len(spans) == 2
        assert spans[0].service_name == "svc-a"
        assert spans[1].service_name == "svc-b"
