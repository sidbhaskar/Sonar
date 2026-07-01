# Sonar (Version 1) 🚀

**A Terminal-Native Distributed Trace Visualizer**

Sonar is a lightweight, terminal-based User Interface (TUI) designed to visualize distributed traces for local microservices development. It acts as a local OpenTelemetry (OTel) collector, catching telemetry data emitted by backend services and rendering the execution path of a single request across multiple network boundaries (HTTP, gRPC, and message brokers) in real-time, entirely within your command line.

---

## 📸 Screenshots

<img width="1332" height="727" alt="image" src="https://github.com/user-attachments/assets/5fea8e3d-eb74-4b33-9259-53b4a2f6a82c" />

---

## ⚡ The Problem

When developing microservices locally, tracking the lifecycle of a single request is incredibly difficult. 
- **The Log Scavenger Hunt:** Manually tailing logs across multiple tabs and copy-pasting correlation IDs.
- **Heavy Tooling:** Running cloud-native tools like Jaeger locally requires Docker, browsers, and high resource usage.
- **Context Switching:** Breaking flow to switch from the terminal to a browser.

## 💡 The Solution

Sonar bridges the gap by running directly in your terminal. It instantly processes OpenTelemetry data in memory and draws an interactive, hierarchical tree representing the request's journey—highlighting errors and isolating payloads with zero context-switching.

## ✨ Core Features

- **OTLP Ingestion:** Native OpenTelemetry Protocol data ingestion (no custom config needed on backend services, just point to localhost).
- **Live ASCII Dependency Tree:** Visually maps parent-child relationships using Unicode box-drawing characters.
- **Instant Payload Inspection:** Dedicated side-panel for raw metadata, HTTP headers, gRPC statuses, and more.
- **Error State Bubbling:** Automatically highlights failed spans and propagates warnings up the tree.
- **Fuzzy Search & Filtering:** Find traces fast by HTTP path, service name, or trace ID.

## 🛠️ Architecture Under the Hood

1. **Instrumentation:** Attach the standard OpenTelemetry agent to your services.
2. **Ingestion Engine:** A built-in asynchronous Python server listens for OTLP spans and parses them into a local datastore.
3. **State & UI Renderer:** Built with [Textual](https://github.com/Textualize/textual), the interface dynamically updates the tree and data tables as traces arrive.

## 🚀 Getting Started

### 1. Install Sonar
Since Sonar is packaged with standard Python tools, you can install it globally or in a virtual environment directly via pip:

```bash
# Clone the repository
git clone https://github.com/your-username/sonar.git
cd sonar

# Install the package and its dependencies
pip install .
```

### 2. Start Sonar
Once installed, a global `sonar` command is added to your terminal. Simply run:

```bash
sonar
```
Sonar will instantly start up its TUI and spin up background listeners on `localhost:4317` (gRPC) and `localhost:4318` (HTTP).

### 3. Connect Your Microservices (Any Framework)

Because Sonar is a compliant OpenTelemetry (OTel) receiver, **you don't need to install any Sonar-specific libraries in your codebase**. You just use the official OpenTelemetry SDKs for your language.

By default, standard OpenTelemetry SDKs attempt to send data to `localhost:4317` (gRPC) or `localhost:4318` (HTTP), which means in many cases, **it just works out of the box** once Sonar is running!

Here's how to explicitly configure common frameworks to point to Sonar:

#### 🟢 Node.js / Express
Use the `@opentelemetry/sdk-node` package and set the exporter endpoint:
```javascript
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');

const sdk = new NodeSDK({
  serviceName: 'my-node-service',
  traceExporter: new OTLPTraceExporter({
    url: 'http://localhost:4318/v1/traces', // Sonar's HTTP endpoint
  }),
});
sdk.start();
```

#### 🐍 Python (FastAPI / Flask / Django)
Install `opentelemetry-exporter-otlp` and configure the tracer:
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
# Exports to localhost:4317 by default (Sonar's gRPC endpoint)
processor = BatchSpanProcessor(OTLPSpanExporter()) 
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
```

#### ☕ Java (Spring Boot)
The easiest way is to use the **OpenTelemetry Java Agent** (no code changes required!). Just run your `.jar` with the agent attached:
```bash
java -javaagent:path/to/opentelemetry-javaagent.jar \
     -Dotel.service.name=my-spring-boot-service \
     -Dotel.exporter.otlp.endpoint=http://localhost:4318 \
     -jar myapp.jar
```

#### 🐹 Go
Use the `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` package:
```go
import "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"

exporter, err := otlptracegrpc.New(ctx, 
    otlptracegrpc.WithInsecure(),
    otlptracegrpc.WithEndpoint("localhost:4317"), // Sonar's gRPC endpoint
)
```

### 4. Watch the Magic Happen ✨
As soon as your services handle a request, they will beam the telemetry data to Sonar. The TUI will instantly populate with a live dependency tree of your request's journey!
