"""gRPC server for OTLP trace ingestion.

Implements the OpenTelemetry Collector TraceService/Export gRPC endpoint
on port 4317 (the standard OTLP gRPC port).  Parsed spans are stored
in the same shared ``trace_store`` used by the HTTP server and the TUI.
"""

from __future__ import annotations

import logging
from concurrent import futures
from typing import Any

import grpc
from google.protobuf.json_format import MessageToDict

from opentelemetry.proto.collector.trace.v1 import (
    trace_service_pb2,
    trace_service_pb2_grpc,
)

from sonar.ingestion.server import parse_otlp_payload, trace_store

logger = logging.getLogger(__name__)


class TraceServiceServicer(trace_service_pb2_grpc.TraceServiceServicer):
    """gRPC servicer that accepts OTLP trace exports.

    Converts the incoming protobuf ``ExportTraceServiceRequest`` to a
    JSON-compatible dict and reuses ``parse_otlp_payload()`` from the
    HTTP server so all parsing logic is shared.
    """

    def Export(
        self,
        request: trace_service_pb2.ExportTraceServiceRequest,
        context: grpc.ServicerContext,
    ) -> trace_service_pb2.ExportTraceServiceResponse:
        """Handle an incoming OTLP/gRPC trace export."""
        try:
            # Convert protobuf to dict (same shape as OTLP/HTTP JSON).
            payload: dict[str, Any] = MessageToDict(
                request,
                preserving_proto_field_name=True,
            )

            spans = parse_otlp_payload(payload)

            if spans:
                trace_store.add_spans(spans)
                logger.debug(
                    "gRPC: ingested %d spans across traces", len(spans)
                )

        except Exception as exc:
            logger.error(
                "gRPC: failed to process trace export: %s",
                exc,
                exc_info=True,
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))

        return trace_service_pb2.ExportTraceServiceResponse()


def serve_grpc(port: int = 4317) -> None:
    """Start the gRPC server and block until termination.

    This is designed to be called from a daemon thread — when the main
    process exits, the thread (and this server) will be killed.

    Args:
        port: The port to listen on.  Defaults to 4317.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(
        TraceServiceServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("gRPC OTLP server listening on port %d", port)
    server.wait_for_termination()
