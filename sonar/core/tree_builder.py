"""Builds hierarchical span trees from flat span lists."""

from __future__ import annotations

from dataclasses import dataclass, field

from sonar.ingestion.models import Span


@dataclass
class TreeNode:
    """A node in the span tree, wrapping a Span with its children.

    Attributes:
        span: The underlying Span data for this node.
        children: Ordered list of child TreeNodes.
    """

    span: Span
    children: list[TreeNode] = field(default_factory=list)


def build_tree(spans: list[Span]) -> list[TreeNode]:
    """Build a nested tree from a flat list of spans.

    Spans whose parent_span_id is None are treated as root nodes.
    Each span is placed under its parent based on parent_span_id matching
    another span's span_id.

    Orphan spans (whose parent_span_id references a span not in the list)
    are promoted to roots so no data is silently dropped.

    Args:
        spans: A flat list of Span objects, in any order.

    Returns:
        A list of root TreeNode objects with children populated recursively.
    """
    if not spans:
        return []

    # Create a TreeNode for every span, indexed by span_id.
    nodes: dict[str, TreeNode] = {
        span.span_id: TreeNode(span=span) for span in spans
    }

    roots: list[TreeNode] = []

    for span in spans:
        if span.parent_span_id is None:
            # Root span — no parent.
            roots.append(nodes[span.span_id])
        else:
            parent = nodes.get(span.parent_span_id)
            if parent is not None:
                parent.children.append(nodes[span.span_id])
            else:
                # Orphan — parent not in this span list; promote to root.
                roots.append(nodes[span.span_id])

    return roots
