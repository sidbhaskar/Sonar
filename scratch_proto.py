import json
from opentelemetry.proto.trace.v1.trace_pb2 import TracesData
from google.protobuf.json_format import MessageToDict

data = TracesData()
span = data.resource_spans.add().scope_spans.add().spans.add()
span.trace_id = b'\x00'*15 + b'\x01'
span.span_id = b'\x00'*7 + b'\x01'
dict_data = MessageToDict(data)
print("Protobuf to Dict:\n" + json.dumps(dict_data, indent=2))