"""Tests for sonar.core.tree_builder.build_tree."""

import pytest

from sonar.core.tree_builder import TreeNode, build_tree
from sonar.ingestion.models import Span


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(
    span_id: str,
    parent_span_id: str | None = None,
    name: str = "op",
    service_name: str = "svc",
) -> Span:
    """Create a minimal Span for testing with sensible defaults."""
    return Span(
        span_id=span_id,
        trace_id="trace-1",
        parent_span_id=parent_span_id,
        name=name,
        service_name=service_name,
        start_time=0,
        end_time=1_000_000,  # 1 ms
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildTreeEmpty:
    """An empty span list should produce an empty tree."""

    def test_returns_empty_list(self):
        result = build_tree([])
        assert result == []


class TestBuildTreeSingleRoot:
    """A single root span with no children."""

    def test_single_root_no_children(self):
        root_span = _make_span("root")
        roots = build_tree([root_span])

        assert len(roots) == 1
        assert roots[0].span is root_span
        assert roots[0].children == []


class TestBuildTreeThreeLevels:
    """A 3-level deep tree: root -> child -> grandchild."""

    @pytest.fixture()
    def spans(self):
        return [
            _make_span("root", name="gateway"),
            _make_span("child", parent_span_id="root", name="billing"),
            _make_span("grandchild", parent_span_id="child", name="db-query"),
        ]

    def test_single_root(self, spans):
        roots = build_tree(spans)
        assert len(roots) == 1

    def test_root_has_one_child(self, spans):
        root = build_tree(spans)[0]
        assert len(root.children) == 1
        assert root.children[0].span.span_id == "child"

    def test_child_has_one_grandchild(self, spans):
        root = build_tree(spans)[0]
        child = root.children[0]
        assert len(child.children) == 1
        assert child.children[0].span.span_id == "grandchild"

    def test_grandchild_is_leaf(self, spans):
        root = build_tree(spans)[0]
        grandchild = root.children[0].children[0]
        assert grandchild.children == []


class TestBuildTreeMultipleChildren:
    """A root span with multiple children (fan-out)."""

    @pytest.fixture()
    def spans(self):
        return [
            _make_span("root", name="api-gateway"),
            _make_span("child-a", parent_span_id="root", name="inventory"),
            _make_span("child-b", parent_span_id="root", name="billing"),
            _make_span("child-c", parent_span_id="root", name="notifications"),
        ]

    def test_single_root(self, spans):
        roots = build_tree(spans)
        assert len(roots) == 1

    def test_root_has_three_children(self, spans):
        root = build_tree(spans)[0]
        assert len(root.children) == 3

    def test_children_ids(self, spans):
        root = build_tree(spans)[0]
        child_ids = [child.span.span_id for child in root.children]
        assert child_ids == ["child-a", "child-b", "child-c"]

    def test_all_children_are_leaves(self, spans):
        root = build_tree(spans)[0]
        for child in root.children:
            assert child.children == []


class TestBuildTreeOrphanSpans:
    """Spans referencing a parent not in the list are promoted to roots."""

    def test_orphan_becomes_root(self):
        orphan = _make_span("orphan", parent_span_id="missing-parent")
        roots = build_tree([orphan])

        assert len(roots) == 1
        assert roots[0].span is orphan


class TestBuildTreeInputOrder:
    """build_tree must work regardless of span arrival order."""

    def test_reverse_order_children_before_parent(self):
        """Spans arrive grandchild-first — tree should still build correctly."""
        spans = [
            _make_span("grandchild", parent_span_id="child", name="db-query"),
            _make_span("child", parent_span_id="root", name="billing"),
            _make_span("root", name="gateway"),
        ]
        roots = build_tree(spans)

        assert len(roots) == 1
        assert roots[0].span.span_id == "root"
        assert len(roots[0].children) == 1
        assert roots[0].children[0].span.span_id == "child"
        assert roots[0].children[0].children[0].span.span_id == "grandchild"
