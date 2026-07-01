# Sonar (Version 1) 🚀

**A Terminal-Native Distributed Trace Visualizer**

Sonar is a lightweight, terminal-based User Interface (TUI) designed to visualize distributed traces for local microservices development. It acts as a local OpenTelemetry (OTel) collector, catching telemetry data emitted by backend services and rendering the execution path of a single request across multiple network boundaries (HTTP, gRPC, and message brokers) in real-time, entirely within your command line.

---

## 📸 Screenshots

*(For now, these are placeholders. Take screenshots of the TUI running and save them in a `docs/` folder as `screenshot-main.png` and `screenshot-details.png` to display them here!)*

![Sonar TUI Main View](docs/screenshot-main.png)
> **Main View:** Live ASCII Dependency Tree of incoming traces.

![Sonar Span Details](docs/screenshot-details.png)
> **Span Details:** Instant Payload Inspection showing raw metadata, gRPC statuses, and database queries.

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

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Run Sonar:**
   ```bash
   python -m sonar.main
   ```
3. **Send Traces:**
   Configure your microservices to send OpenTelemetry data to `localhost:4318`. Or, use the included test scripts to generate mock traces!
