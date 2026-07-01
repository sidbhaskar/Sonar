"""Textual TUI application for Sonar.

Provides a terminal-native interface with a trace list (left rail),
span tree (center), and live polling of the in-memory trace store.
"""

from __future__ import annotations

import dataclasses
import json
import time
from typing import Any

from rich.text import Text
from rich.table import Table
from rich.syntax import Syntax
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, ListView, ListItem, Tree, Input
from textual import on

from sonar.core.tree_builder import TreeNode, build_tree
from sonar.ingestion.models import Span
from sonar.ingestion.store import TraceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROTO_COLORS: dict[str, str] = {
    "http": "#7fd8d8",   # $cyan
    "grpc": "#e8c468",   # $amber
    "kafka": "#c98fff",  # $purple
}


def detect_protocol(span: Span) -> str | None:
    """Detect protocol type from span attributes."""
    attrs = span.attributes
    if attrs.get("rpc.system") == "grpc":
        return "grpc"
    if attrs.get("messaging.system") == "kafka":
        return "kafka"
    if any(k.startswith("http.") for k in attrs):
        return "http"
    return None


def has_error(spans: list[Span]) -> bool:
    """Check if any span in the list has ERROR status."""
    return any(s.status == "ERROR" for s in spans)


def _subtree_has_error(node: TreeNode) -> bool:
    """Check if this node or any descendant has ERROR status."""
    if node.span.status == "ERROR":
        return True
    return any(_subtree_has_error(child) for child in node.children)


def format_span_label(span: Span, descendant_error: bool = False) -> Text:
    """Build a Rich Text label for a single span tree node.

    Follows the per-row anatomy from design.md Section 5:
      [error marker] name  (service)  [protocol]  duration
    """
    label = Text()

    # 1. Error marker — red ✕ if this span itself errored
    if span.status == "ERROR":
        label.append("✕ ", style="bold #ff6b6b")
    elif descendant_error:
        # Propagated error: dim red marker for "a descendant failed"
        label.append("! ", style="#5a2424")

    # 2. Span name — red if errored, default $text otherwise
    name_style = "#ff6b6b" if span.status == "ERROR" else "#c9d6c4"
    label.append(span.name, style=name_style)

    # 3. Service name in parentheses, dimmed
    label.append(f"  ({span.service_name})", style="#5f7a5a")

    # 4. Protocol badge, colored per protocol table
    proto = detect_protocol(span)
    if proto:
        color = PROTO_COLORS.get(proto, "#5f7a5a")
        label.append(f"  [{proto}]", style=color)

    # 5. Duration, dimmed (red if errored)
    dur_style = "#ff6b6b" if span.status == "ERROR" else "#5f7a5a"
    label.append(f"  {span.duration_ms:.0f}ms", style=dur_style)

    return label


# ---------------------------------------------------------------------------
# Custom Widgets
# ---------------------------------------------------------------------------

class TraceListItem(ListItem):
    """A trace entry in the left-rail trace list.

    Renders 3 lines per the design spec (Section 6):
        ✓ 7f3a9c21
          POST /checkout
          812ms · 5 spans
    """

    def __init__(self, trace_id: str, spans: list[Span]) -> None:
        super().__init__()
        self.trace_id = trace_id
        self.trace_spans = spans

    def compose(self) -> ComposeResult:
        root = next(
            (s for s in self.trace_spans if s.parent_span_id is None),
            self.trace_spans[0],
        )
        err = has_error(self.trace_spans)

        # Line 1: status glyph + trace_id (first 8 chars)
        line1 = Text()
        if err:
            line1.append("✕ ", style="bold #ff6b6b")
        else:
            line1.append("✓ ", style="#2c6b4a")
        line1.append(self.trace_id[:8], style="#7fd8d8")

        # Line 2: route / operation name
        line2 = Text(f"  {root.name}", style="#c9d6c4")

        # Line 3: total trace duration (max end - min start) · span count
        trace_start = min(s.start_time for s in self.trace_spans)
        trace_end = max(s.end_time for s in self.trace_spans)
        trace_duration_ms = (trace_end - trace_start) / 1_000_000
        line3 = Text(
            f"  {trace_duration_ms:.0f}ms · {len(self.trace_spans)} spans",
            style="#5f7a5a",
        )

        yield Static(line1, classes="trace-item-line")
        yield Static(line2, classes="trace-item-line")
        yield Static(line3, classes="trace-item-line")


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class SonarApp(App):
    """Sonar — Terminal-native distributed trace visualizer."""

    TITLE = "Sonar"

    CSS = """
    /* ── Global ────────────────────────────────────────── */
    Screen {
        background: #0b0e0c;
        color: #c9d6c4;
    }

    /* ── Top Bar ───────────────────────────────────────── */
    #header-container {
        dock: top;
        height: auto;
        background: #0e120e;
        border-bottom: solid #1f2a1f;
    }

    #top-bar {
        height: 1;
        width: 100%;
        background: #0e120e;
        padding: 0 2;
    }

    /* ── Search Bar ────────────────────────────────────── */
    #search-bar {
        height: 3;
        background: #0e120e;
        padding: 0 1;
    }

    #search-input {
        background: #0b0e0c;
        border: tall #1f2a1f;
        color: #c9d6c4;
    }

    #search-input:focus {
        border: tall #6fffb0;
    }

    #search-input.-placeholder {
        color: #3c4a3a;
    }

    /* ── Main Content Area ─────────────────────────────── */
    #main-area {
        height: 1fr;
    }

    .panel-title {
        height: 1;
        width: 100%;
        background: #141a13;
        color: #5f7a5a;
        text-style: bold;
        padding: 0 1;
    }

    /* ── Trace List (Left Rail, ~28 cols) ──────────────── */
    #trace-list-panel {
        width: 32;
        min-width: 24;
        background: #0a0d0a;
        border-right: solid #1f2a1f;
    }

    #trace-list {
        background: #0a0d0a;
        scrollbar-background: #0a0d0a;
        scrollbar-color: #1f2a1f;
        scrollbar-color-hover: #5f7a5a;
        margin-top: 1;
        height: 1fr;
    }

    #trace-list-empty {
        display: none;
        height: 1fr;
        color: #5f7a5a;
        text-align: center;
        content-align: center middle;
    }

    TraceListItem {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        background: #0a0d0a;
        border-left: wide transparent;
    }

    TraceListItem.--highlight {
        background: #111611;
        border-left: wide #6fffb0;
    }

    .trace-item-line {
        height: 1;
        background: transparent;
    }

    /* ── Span Tree (Center, flexible width) ────────────── */
    #span-tree-panel {
        background: #0b0e0c;
        width: 1fr;
        min-width: 40;
    }

    #span-tree-content {
        padding: 1 2;
        height: 1fr;
    }

    #span-tree {
        background: #0b0e0c;
        scrollbar-background: #0b0e0c;
        scrollbar-color: #1f2a1f;
        scrollbar-color-hover: #5f7a5a;
    }

    Tree > .tree--guides {
        color: #1f2a1f;
    }

    Tree > .tree--cursor {
        background: #1a2018;
        text-style: bold;
    }

    Tree > .tree--highlight {
        background: #151a14;
    }

    /* ── Inspector (Right Rail, ~40 cols) ──────────────── */
    #inspector-panel {
        width: 44;
        min-width: 36;
        background: #10140f;
        border-left: solid #1f2a1f;
    }

    #inspector-body {
        padding: 1 2;
        height: 1fr;
    }

    #inspector-placeholder {
        content-align: center middle;
        color: #3c4a3a;
        height: 100%;
    }

    #inspector-content {
        display: none;
        scrollbar-background: #10140f;
        scrollbar-color: #1f2a1f;
        scrollbar-color-hover: #5f7a5a;
    }

    #inspector-header {
        margin-bottom: 1;
    }

    #inspector-subheader {
        margin-bottom: 1;
        border-bottom: dashed #1f2a1f;
        padding-bottom: 1;
    }

    #inspector-attributes {
        margin-bottom: 1;
    }

    #inspector-divider {
        color: #3c4a3a;
        margin-bottom: 1;
    }

    #inspector-payload {
        background: #0b0e0c;
        border: solid #1f2a1f;
        padding: 1;
    }

    /* ── Status Bar ────────────────────────────────────── */
    #status-bar {
        dock: bottom;
        height: 1;
        width: 100%;
        background: #0e120e;
        padding: 0 2;
    }

    /* ── Empty State ───────────────────────────────────── */
    #empty-state {
        content-align: center middle;
        color: #3c4a3a;
        width: 100%;
        height: 100%;
    }

    /* ── Error Filter Indicator ────────────────────────── */
    #error-filter-badge {
        display: none;
        height: 1;
        padding: 0 1;
        color: #ff6b6b;
        background: #1a1010;
    }

    #error-filter-badge.active {
        display: block;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True, show=False),
        Binding("slash", "focus_search", "Search", priority=True, show=False),
        Binding("e", "toggle_errors", "Errors Only", priority=True, show=False),
        Binding("i", "toggle_inspector", "Toggle Inspector", priority=True, show=False),
        Binding("escape", "unfocus_search", "Back", priority=True, show=False),
    ]

    def __init__(self, trace_store: TraceStore | None = None) -> None:
        super().__init__()
        self._trace_store = trace_store if trace_store is not None else TraceStore()
        self._start_time = time.time()
        self._known_trace_ids: set[str] = set()
        self._errors_only: bool = False
        self._pulse_on: bool = True
        self._inspector_visible: bool = True

    # ── Compose ──────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="header-container"):
            yield Static(id="top-bar")
            with Horizontal(id="search-bar"):
                yield Input(
                    placeholder="Search traces... (press / to focus)",
                    id="search-input",
                )
        with Horizontal(id="main-area"):
            with Vertical(id="trace-list-panel"):
                yield Static(" ▎TRACES", classes="panel-title")
                yield Static(id="error-filter-badge")
                yield ListView(id="trace-list")
                yield Static(
                    "No traces yet\nAwaiting telemetry data…",
                    id="trace-list-empty",
                )
            with Vertical(id="span-tree-panel"):
                yield Static(" ▎SPAN TREE", classes="panel-title")
                with Vertical(id="span-tree-content"):
                    yield Static(
                        "── waiting for traces ──\n\n"
                        "Point your OTel exporter at\n"
                        "  http://localhost:4318  (HTTP)\n"
                        "  localhost:4317         (gRPC)\n\n"
                        "Traces will appear here automatically.",
                        id="empty-state",
                    )
                    yield Tree("Spans", id="span-tree")
            with Vertical(id="inspector-panel"):
                yield Static(" ▎INSPECTOR", classes="panel-title")
                with Vertical(id="inspector-body"):
                    yield Static(
                        "Select a span to inspect",
                        id="inspector-placeholder",
                    )
                    with VerticalScroll(id="inspector-content"):
                        yield Static(id="inspector-header")
                        yield Static(id="inspector-subheader")
                        yield Static(id="inspector-attributes")
                        yield Static(
                            "── raw payload ──",
                            id="inspector-divider",
                        )
                        yield Static(id="inspector-payload")
        yield Static(id="status-bar")

    # ── Lifecycle ────────────────────────────────────────

    def on_mount(self) -> None:
        """Configure initial state and start polling."""
        # Hide span tree until a trace is selected.
        tree = self.query_one("#span-tree", Tree)
        tree.display = False
        tree.show_root = False

        # Set initial focus to trace list so keybindings work immediately.
        self.query_one("#trace-list", ListView).focus()

        # Polling: 1-second intervals.
        self.set_interval(1.0, self._poll_traces)
        self.set_interval(1.0, self._tick_top_bar)

        # Initial render of chrome.
        self._render_top_bar()
        self._render_status_bar()

    # ── Top Bar (Section 8) ──────────────────────────────

    def _tick_top_bar(self) -> None:
        """Called every second to pulse the live dot and update metrics."""
        self._pulse_on = not self._pulse_on
        self._render_top_bar()

    def _render_top_bar(self) -> None:
        uptime = time.time() - self._start_time
        mins, secs = divmod(int(uptime), 60)

        bar = self.query_one("#top-bar", Static)
        content = Text()

        # Pulsing live dot (~2s cycle: 1s bright, 1s dim)
        dot_style = "bold #6fffb0" if self._pulse_on else "#2c6b4a"
        content.append("\u25cf ", style=dot_style)
        content.append("sonar", style="bold #6fffb0")

        sep = "  \u2502  "
        content.append(sep, style="#1f2a1f")
        content.append("http ", style="#5f7a5a")
        content.append(":4318", style="#c9d6c4")
        content.append("  ", style="#1f2a1f")
        content.append("grpc ", style="#5f7a5a")
        content.append(":4317", style="#c9d6c4")

        content.append(sep, style="#1f2a1f")
        content.append("traces ", style="#5f7a5a")
        content.append(str(len(self._trace_store)), style="#c9d6c4")

        content.append(sep, style="#1f2a1f")
        content.append("uptime ", style="#5f7a5a")
        content.append(f"{mins}m {secs:02d}s", style="#c9d6c4")

        bar.update(content)

    # ── Status Bar (Section 8) ───────────────────────────

    def _render_status_bar(self) -> None:
        bar = self.query_one("#status-bar", Static)
        content = Text()

        bindings = [
            ("\u2191\u2193", "navigate"),
            ("\u21b5", "inspect"),
            ("/", "search"),
            ("e", "errors only"),
            ("i", "inspector"),
            ("q", "quit"),
        ]
        for i, (key, action) in enumerate(bindings):
            if i > 0:
                content.append("    ", style="#3c4a3a")
            content.append(key, style="bold #6fffb0")
            content.append(f" {action}", style="#5f7a5a")

        bar.update(content)

    # ── Trace List Polling ───────────────────────────────

    def _poll_traces(self) -> None:
        """Check for new traces every second and refresh the list."""
        current_ids = self._trace_store.trace_ids()
        if current_ids != self._known_trace_ids:
            self._known_trace_ids = current_ids.copy()
            self._refresh_trace_list()

    def _refresh_trace_list(self) -> None:
        """Rebuild the trace list, applying search and error filters."""
        search_text = self.query_one("#search-input", Input).value.strip().lower()
        lv = self.query_one("#trace-list", ListView)
        lv.clear()

        # Iterate newest-first (reversed insertion order from TraceStore).
        all_traces = self._trace_store.all_traces()
        matched = 0
        for trace_id, spans in reversed(all_traces):
            # Error-only filter.
            if self._errors_only and not has_error(spans):
                continue

            # Text search filter (matches trace_id, route, service names).
            if search_text:
                root = next(
                    (s for s in spans if s.parent_span_id is None),
                    spans[0],
                )
                svc_names = " ".join(s.service_name.lower() for s in spans)
                searchable = (
                    f"{trace_id.lower()} {root.name.lower()} {svc_names}"
                )
                if search_text not in searchable:
                    continue

            lv.append(TraceListItem(trace_id, spans))
            matched += 1

        # Toggle empty states.
        empty_main = self.query_one("#empty-state", Static)
        tree = self.query_one("#span-tree", Tree)
        trace_list_empty = self.query_one("#trace-list-empty", Static)

        if len(self._trace_store) == 0:
            empty_main.display = True
            tree.display = False
            trace_list_empty.display = True
            lv.display = False
            trace_list_empty.update("No traces yet\nAwaiting telemetry data…")
        else:
            trace_list_empty.display = False
            lv.display = True
            if matched == 0 and (search_text or self._errors_only):
                trace_list_empty.update("No matching traces")
                trace_list_empty.display = True
                lv.display = False

        # Update error filter badge.
        badge = self.query_one("#error-filter-badge", Static)
        if self._errors_only:
            badge.update(Text("▸ errors only", style="#ff6b6b"))
            badge.add_class("active")
        else:
            badge.remove_class("active")

    # ── Span Tree Rendering (Section 5) ──────────────────

    @on(ListView.Selected, "#trace-list")
    def _on_trace_selected(self, event: ListView.Selected) -> None:
        """When a trace is selected, render its span tree."""
        item = event.item
        if isinstance(item, TraceListItem):
            self._render_span_tree(item.trace_spans)

    def _render_span_tree(self, spans: list[Span]) -> None:
        """Build and display the span tree for the selected trace."""
        tree_widget = self.query_one("#span-tree", Tree)
        empty = self.query_one("#empty-state", Static)

        # Reset inspector when a new trace is selected.
        self.query_one("#inspector-placeholder", Static).display = True
        self.query_one("#inspector-content", VerticalScroll).display = False

        empty.display = False
        tree_widget.display = True
        tree_widget.clear()

        roots = build_tree(spans)
        for root_node in roots:
            self._add_tree_node(tree_widget.root, root_node)

        # Always fully expanded per design spec (Section 5).
        tree_widget.root.expand_all()

    def _add_tree_node(self, parent: Any, tree_node: TreeNode) -> None:
        """Recursively add a TreeNode and its children to the Textual Tree."""
        # Check if any descendant (not self) has an error — for propagation.
        descendant_err = (
            tree_node.span.status != "ERROR"
            and _subtree_has_error(tree_node)
        )
        label = format_span_label(tree_node.span, descendant_error=descendant_err)

        if tree_node.children:
            branch = parent.add(label, data=tree_node.span)
            for child in tree_node.children:
                self._add_tree_node(branch, child)
        else:
            parent.add_leaf(label, data=tree_node.span)

    @on(Tree.NodeSelected, "#span-tree")
    def _on_span_selected(self, event: Tree.NodeSelected) -> None:
        """When a span in the tree is selected, render its details."""
        if isinstance(event.node.data, Span):
            self._render_inspector(event.node.data)

    def _render_inspector(self, span: Span) -> None:
        """Render the details of a single span in the right rail."""
        placeholder = self.query_one("#inspector-placeholder", Static)
        content = self.query_one("#inspector-content", VerticalScroll)

        placeholder.display = False
        content.display = True

        # 1. Header
        header = self.query_one("#inspector-header", Static)
        header_text = Text()
        if span.status == "ERROR":
            header_text.append("✕ ", style="bold #ff6b6b")
        header_text.append(span.name, style="bold #6fffb0")
        header.update(header_text)

        # 2. Subheader
        subheader = self.query_one("#inspector-subheader", Static)
        proto = detect_protocol(span) or "unknown"
        subheader.update(
            Text(
                f"{span.service_name} · {proto.upper()} · {span.duration_ms:.0f}ms",
                style="#5f7a5a",
            )
        )

        # 3. Attributes
        attr_container = self.query_one("#inspector-attributes", Static)
        error_keywords = ["fail", "error", "exceeded", "declined"]

        table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        table.add_column("Key", style="#5f7a5a")
        table.add_column("Value")

        for k, v in span.attributes.items():
            v_str = str(v)
            is_err = any(kw in v_str.lower() for kw in error_keywords) or any(
                kw in k.lower() for kw in error_keywords
            )
            val_style = "#ff6b6b" if is_err else "#c9d6c4"
            table.add_row(k, Text(v_str, style=val_style))

        attr_container.update(table)

        # 4. Payload
        payload_container = self.query_one("#inspector-payload", Static)
        raw_dict = dataclasses.asdict(span)
        # Include duration_ms for completeness (it's a property)
        raw_dict["duration_ms"] = span.duration_ms
        payload_str = json.dumps(raw_dict, indent=2)

        syntax = Syntax(
            payload_str,
            "json",
            theme="ansi_dark",
            background_color="default",
            word_wrap=True,
        )
        payload_container.update(syntax)

    # ── Actions ──────────────────────────────────────────

    def action_focus_search(self) -> None:
        """Move focus to the search input (triggered by /)."""
        self.query_one("#search-input", Input).focus()

    def action_unfocus_search(self) -> None:
        """Move focus back to the trace list (triggered by Escape)."""
        self.query_one("#trace-list", ListView).focus()

    def action_toggle_errors(self) -> None:
        """Toggle error-only filter on the trace list."""
        self._errors_only = not self._errors_only
        self._refresh_trace_list()

    def action_toggle_inspector(self) -> None:
        """Toggle the inspector panel visibility (triggered by i)."""
        panel = self.query_one("#inspector-panel", Vertical)
        self._inspector_visible = not self._inspector_visible
        panel.display = self._inspector_visible

    @on(Input.Changed, "#search-input")
    def _on_search_changed(self, event: Input.Changed) -> None:
        """Live-filter the trace list as the user types."""
        self._refresh_trace_list()
