# Sonar — UI/UX Design Specification

This document describes the visual design and interaction model for Sonar's
terminal UI. It is derived from an approved HTML/CSS prototype and is intended
as an implementation reference for the Textual (Python TUI) build. Follow it
as the source of truth for layout, color, typography, and interaction
behavior — do not invent new UI patterns not described here.

---

## 1. Design Philosophy

Sonar should feel like a **native terminal tool**, not a web app squeezed
into a terminal. Reference points: htop, lazygit, k9s. Specific principles:

- **Monospace-first, information-dense.** No wasted whitespace, no large
  decorative elements. Every pixel/cell carries information.
- **Dark, low-luminance background.** This is a tool developers keep open in
  a pane for hours; it must not strain the eyes or compete for attention with
  adjacent panes.
- **Color is signal, not decoration.** Color is used exclusively to encode
  meaning (error vs ok, protocol type, active selection). Never use color
  purely for visual variety.
- **Keyboard-first, mouse-optional.** Every action must be reachable via
  keyboard. Mouse/click support (if the terminal supports it) is a bonus
  layer, not the primary interaction model.
- **Zero motion unless meaningful.** Avoid animation for its own sake. The
  one exception is a subtle "live" pulse indicator showing the ingestion
  server is actively listening — this communicates real-time state, which
  matters for a live-monitoring tool.

---

## 2. Layout Structure

Three-pane layout, fixed regions, no overlapping modals for core flows.

```
┌─────────────────────────────────────────────────────────────────┐
│ TOP BAR: brand · live indicator · port · trace count · uptime   │
├─────────────────────────────────────────────────────────────────┤
│ SEARCH BAR: filter input (triggered by "/")                     │
├───────────────┬─────────────────────────────────┬───────────────┤
│               │                                   │               │
│  TRACE LIST   │         SPAN TREE                │   INSPECTOR   │
│  (left rail)  │         (center)                 │   (right)     │
│               │                                   │               │
│  fixed width  │         flexible width            │  fixed width  │
│  ~28 cols     │         (largest region)          │  ~40 cols     │
│               │                                   │               │
├───────────────┴─────────────────────────────────┴───────────────┤
│ STATUS BAR: keybinding hints (left) · build info (right)        │
└─────────────────────────────────────────────────────────────────┘
```

- **Top bar**: always visible. Shows brand name, a pulsing "live" dot,
  listening port, total traces captured, and process uptime.
- **Search bar**: always visible, directly below top bar. Not a popup/modal.
- **Trace list (left rail)**: scrollable list of recently captured traces,
  newest first. This is the entry point — nothing in the center/right panes
  renders until a trace is selected here.
- **Span tree (center)**: the primary content area. Renders the selected
  trace as a hierarchical ASCII tree. This pane should always get the most
  horizontal space, since the tree is the core value of the tool.
- **Inspector (right rail)**: shows full detail for the currently selected
  *span* (not trace). Empty/placeholder state when nothing is selected.
- **Status bar**: always visible. Static keybinding legend, not interactive.

### Responsive behavior
At minimum terminal width (~80 cols), collapse the inspector panel and
require an explicit keystroke (e.g. `i`) to toggle it as an overlay instead
of a fixed column. Do not attempt to shrink the trace list or tree below
their minimum usable widths (~20 cols / ~40 cols respectively) — collapse
the inspector first.

---

## 3. Color System

Define as named theme tokens (Textual CSS variables), not hardcoded hex
values scattered through widget code.

| Token | Hex | Usage |
|---|---|---|
| `$bg` | `#0b0e0c` | App background |
| `$panel` | `#10140f` | Inspector / search bar background |
| `$panel-alt` | `#0a0d0a` | Trace list background |
| `$line` | `#1f2a1f` | Borders, dividers, dashed separators |
| `$text` | `#c9d6c4` | Primary text |
| `$dim` | `#5f7a5a` | Secondary/muted text, labels |
| `$dim-2` | `#3c4a3a` | Tertiary text, placeholders, hints |
| `$green` | `#6fffb0` | Brand accent, "live" state, success |
| `$green-dim` | `#2c6b4a` | Success indicators (less prominent) |
| `$amber` | `#e8c468` | gRPC protocol tag |
| `$red` | `#ff6b6b` | Errors — span status, error badges |
| `$red-dim` | `#5a2424` | Error background tints |
| `$cyan` | `#7fd8d8` | HTTP protocol tag |
| `$purple` | `#c98fff` | Kafka / message-broker protocol tag |

### Color usage rules
- **Green** = healthy/success/live, used sparingly (brand, ok-status dot,
  pulse indicator). Do not overuse green elsewhere or it loses meaning.
- **Red** = error only. Any span with `status == ERROR` gets red text, a
  red `✕` marker, and that marker propagates visually up the tree to every
  ancestor span (parent nodes should show a subtle red tint or marker
  indicating "a descendant failed," even if the parent itself succeeded).
- **Protocol tags** (HTTP/gRPC/Kafka) each get one fixed, consistent color
  (cyan/amber/purple respectively) shown as a small bordered badge next to
  the span name. This lets a user visually scan a tree and instantly see
  which hops were network calls vs message-broker hops.
- Everything else defaults to `$text` or `$dim` — resist the urge to add
  more colors than this table defines.

---

## 4. Typography

- **Font**: monospace only, full stop. Rely on the terminal's configured
  font; do not attempt custom font loading (not applicable in a TUI, but
  stated here to keep parity with the web prototype's intent).
- **Hierarchy via weight/color/dimness, not size.** Terminal UIs can't
  freely vary font size per-element the way CSS can. Use:
  - Bold + `$green` for primary headers/brand
  - Bold + `$text` for selected/active row
  - Regular + `$dim` for secondary metadata (service name, durations)
  - Regular + `$dim-2` for placeholder/hint text
- **No text truncation without ellipsis indication.** If a route path or
  service name is too long for its column, truncate with `…` rather than
  hard-cutting.

---

## 5. The Span Tree — Core Interaction Element

This is the signature element of the tool and deserves the most care.

### Visual structure
Render using real box-drawing Unicode characters, not ASCII approximations:
- `├── ` for a non-last child at a given depth
- `└── ` for the last child at a given depth
- `│   ` for vertical continuation past a sibling that has more siblings below it
- 2-space indent per depth level beyond the connector itself

Example target output:
```
api-gateway                          (api-gateway)     [http]    812ms
├── inventory-service                (inventory-svc)   [grpc]     94ms
├── ✕ billing-service                (billing-svc)     [grpc]    690ms
│   └── ledger-db                    (postgres)        [http]     12ms
└── order-events                     (kafka)           [kafka]      3ms
```

### Per-row anatomy (left to right)
1. Tree branch connector (dimmed color, `$line`)
2. Error marker `✕` (red, only if this span's own status is ERROR) — note
   this is separate from "a descendant errored," see propagation rule above
3. Span name (`$text`, or `$red` if this span itself errored)
4. Service name in parentheses, dimmed (`$dim`)
5. Protocol badge, color per protocol table above
6. Duration, right-aligned within the row, `$dim` (or `$red` if errored)

### Interaction
- Arrow keys (`↑`/`↓`) move selection between visible spans in the tree.
- `Enter` (or click, where supported) opens/focuses that span's detail in
  the inspector panel — selection and inspection are the same action, there
  is no separate "select" vs "open" step.
- Selected row gets a distinct background tint (`$panel` lightened slightly)
  plus a thin border, not just a color change, so it's legible even for
  colorblind users.
- The tree does not support manual collapse/expand in v1 — always render
  fully expanded. (Note for future: large traces may need this later, but
  v1 should not build collapse state management.)

---

## 6. Trace List (Left Rail)

Each row represents one full trace (one user request's complete journey),
not an individual span. Row anatomy, stacked vertically per item:

```
✓ 7f3a9c21
  POST /checkout
  812ms · 5 spans
```

- **Line 1**: status glyph (`✓` green-dim if no span errored anywhere in
  this trace, `✕` red if any span in the trace has ERROR status) + trace_id
  (monospace hash, `$cyan` optional for scannability).
- **Line 2**: the HTTP route or operation name that triggered this trace
  (e.g. `POST /checkout`) — this is the human-readable label, since trace
  IDs alone are meaningless to a developer scanning the list.
- **Line 3**: total trace duration + span count, both dimmed.
- Selected/active trace gets a left border accent in `$green` plus a
  slightly lighter row background — this must be visually distinct from
  the span-tree's own selection highlight, since both can be "selected"
  simultaneously in different panes.
- List is sorted newest-first by default (most recent trace at top).
- Live updates: when a new trace arrives while the UI is open, it should
  insert at the top of this list without disrupting current scroll position
  or selection elsewhere in the UI.

---

## 7. Inspector Panel (Right Rail)

Shows full detail for whichever span is currently selected in the tree.
Empty state (nothing selected) shows only a muted placeholder line, no
borders or empty boxes.

Populated state, top to bottom:
1. **Header**: span name (with `✕` prefix if errored), in `$green` bold
2. **Subheader**: `service_name · PROTOCOL · duration`, dimmed
3. **Key-value attribute block**: two-column layout, label dimmed/left,
   value `$text`/right. Any value matching error-like patterns (e.g.
   containing "fail", "error", "exceeded", "declined") should render in
   `$red` even within an otherwise normal-looking attributes block — this
   lets a developer's eye catch the failure reason without reading every
   field.
4. **Divider** (dashed, `$line`) labeled "raw payload"
5. **Payload block**: monospace, bordered, slightly different background
   (`$bg`, darker than the panel itself) showing the full JSON
   representation of the span/attributes. If a specific line in the payload
   is the error cause, that line should be highlighted in `$red` rather
   than the whole block.

---

## 8. Top Bar & Status Bar

**Top bar** is a single-row, low-emphasis header — not a navigation
element, purely informational:
- Brand name in `$green` bold, preceded by a small pulsing dot indicating
  the ingestion server is actively listening (this is the one place
  animation is acceptable — subtle opacity pulse, ~2s cycle, not blinking
  or strobing)
- Right-aligned metadata: listening port, total traces captured this
  session, process uptime — all dimmed, all using a consistent
  `label value` pattern where the label is dim and the value is `$text`

**Status bar** is a permanent keybinding legend, not interactive, always
visible at the bottom:
- Left side: current available keybindings as `key` + short action label
  pairs (e.g. `↑↓ navigate`, `↵ inspect`, `/ search`, `e errors only`,
  `q quit`)
- Right side: small static text describing the active backend (e.g.
  "FastAPI ingestion · Textual render · in-memory store") — this is purely
  contextual flavor text, not functional

---

## 9. Search & Filtering

- Triggered by pressing `/` from anywhere outside the input itself, which
  moves focus into the search field — this mirrors vim/less conventions
  developers already know.
- Search filters the **trace list** only (not individual spans within a
  tree) by matching against trace_id, route/operation name, and any service
  name present in that trace's spans.
- Filtering should be live/incremental as the user types, not
  submit-on-enter.
- A separate one-key toggle (`e`) filters the trace list to errored traces
  only, independent of the text search — both filters should be able to
  compose (text search + errors-only simultaneously).

---

## 10. Empty & Edge States

- **No traces yet**: trace list and tree both show a calm placeholder
  message (e.g. "waiting for traces — point your OTel exporter at
  localhost:4318"), not an error state. This is the expected resting state
  when the tool first starts.
- **Trace selected, no span selected**: tree renders normally; inspector
  shows its placeholder state only.
- **Search yields no results**: trace list shows a short "no matching
  traces" message rather than rendering empty.
- **Very long traces** (many spans): tree pane scrolls vertically; do not
  attempt to compress row height or font size to fit more on screen.

---

## 11. What NOT to Build in v1

Explicitly out of scope for the initial UI implementation — do not add
these even if they seem natural extensions:
- Manual tree node collapse/expand
- Multiple simultaneous trace tabs/panes
- Mouse-drag resizing of panels
- Theming/configurable color schemes
- Animations beyond the single live-indicator pulse described in Section 8

---

## 12. Reference Assets

An HTML/CSS prototype demonstrating this exact visual language exists and
should be treated as the canonical visual reference for resolving any
ambiguity not covered by this document. When in doubt about spacing, color
application, or row anatomy, defer to that prototype's behavior over
inventing new patterns.
