"""Tests for SumRope class based on stub signatures."""

import pytest
from sumrope import SumRope
from sumrope.sumrope import RLEGroup, LenPair, LeafNode, BranchNode


class TestSumRopeBasics:
    """Test basic SumRope initialization and properties."""

    def test_init_empty(self):
        """Test initialization with no values."""
        rope = SumRope()
        assert len(rope) == 0

    def test_init_with_values(self):
        """Test initialization with sequence of RLEGroups."""
        groups = [RLEGroup("hello"), RLEGroup("world")]
        rope = SumRope(groups)
        assert len(rope) == 2

    def test_from_text(self):
        """Test creating SumRope from text."""
        rope = SumRope.from_text("hello\nworld")
        assert len(rope) > 0

    def test_len(self):
        """Test __len__ returns number of elements."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        assert len(rope) == 3


class TestSumRopeIndexing:
    """Test SumRope indexing operations."""

    def test_getitem_single_index(self):
        """Test getting single item by index."""
        groups = [RLEGroup("hello"), RLEGroup("world")]
        rope = SumRope(groups)
        item = rope[0]
        assert isinstance(item, LenPair)

    def test_getitem_slice(self):
        """Test getting items by slice."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        items = rope[0:2]
        assert isinstance(items, list)
        assert len(items) == 2

    def test_setitem_single_index(self):
        """Test setting single item by index."""
        groups = [RLEGroup("hello"), RLEGroup("world")]
        rope = SumRope(groups)
        new_group = RLEGroup("test")
        rope[0] = new_group
        # Verify the rope still has valid structure
        assert len(rope) == 2

    def test_setitem_slice(self):
        """Test setting items by slice."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        new_groups = [RLEGroup("x"), RLEGroup("y")]
        rope[0:2] = new_groups
        # Verify the rope still has valid structure
        assert len(rope) >= 1

    def test_get_single(self):
        """Test get_single method."""
        groups = [RLEGroup("hello"), RLEGroup("world")]
        rope = SumRope(groups)
        item = rope.get_single(0)
        assert isinstance(item, LenPair)

    def test_get_range(self):
        """Test get_range method returns items from start to end (exclusive)."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c"), RLEGroup("d")]
        rope = SumRope(groups)
        items = rope.get_range(1, 3)
        assert isinstance(items, list)
        assert len(items) == 2


class TestSumRopeReplace:
    """Test SumRope replace operations."""

    def test_replace_single(self):
        """Test replacing single value."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        rope.replace(1, 1, [RLEGroup("x")])
        assert len(rope) == 3

    def test_replace_multiple(self):
        """Test replacing multiple values."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c"), RLEGroup("d")]
        rope = SumRope(groups)
        rope.replace(1, 2, [RLEGroup("x"), RLEGroup("y"), RLEGroup("z")])
        # Removed 2, added 3, so net +1
        assert len(rope) == 5

    def test_replace_insert(self):
        """Test inserting values (old_count = 0)."""
        groups = [RLEGroup("a"), RLEGroup("b")]
        rope = SumRope(groups)
        rope.replace(1, 0, [RLEGroup("x")])
        assert len(rope) == 3

    def test_replace_delete(self):
        """Test deleting values (new_values empty)."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        rope.replace(1, 1, [])
        assert len(rope) == 2

    def test_replace_at_start(self):
        """Test replacing at the start of the rope."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        rope.replace(0, 1, [RLEGroup("x")])
        assert len(rope) == 3

    def test_replace_at_end(self):
        """Test replacing at the end of the rope."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        rope.replace(2, 1, [RLEGroup("x")])
        assert len(rope) == 3


class TestSumRopeSums:
    """Test SumRope sum operations."""

    def test_prefix_sum(self):
        """Test prefix_sum returns sum of items [0:index)."""
        groups = [RLEGroup("a"), RLEGroup("bb"), RLEGroup("ccc")]
        rope = SumRope(groups)
        sum0 = rope.prefix_sum(0)
        assert isinstance(sum0, LenPair)
        assert sum0.charlen == 0
        assert sum0.bytelen == 0

        sum1 = rope.prefix_sum(1)
        assert sum1.charlen == 1
        assert sum1.bytelen == 1

    def test_range_sum(self):
        """Test range_sum returns sum of values in [start:end)."""
        groups = [RLEGroup("a"), RLEGroup("bb"), RLEGroup("ccc")]
        rope = SumRope(groups)
        sum_range = rope.range_sum(0, 2)
        assert isinstance(sum_range, LenPair)
        # "a" + "bb" = 3 chars, 3 bytes
        assert sum_range.charlen == 3
        assert sum_range.bytelen == 3

    def test_total_sum(self):
        """Test total_sum returns sum of all values."""
        groups = [RLEGroup("a"), RLEGroup("bb"), RLEGroup("ccc")]
        rope = SumRope(groups)
        total = rope.total_sum()
        assert isinstance(total, LenPair)
        # "a" + "bb" + "ccc" = 6 chars, 6 bytes
        assert total.charlen == 6
        assert total.bytelen == 6

    def test_sum_with_unicode(self):
        """Test sums work correctly with Unicode characters."""
        groups = [RLEGroup("café"), RLEGroup("🌍")]
        rope = SumRope(groups)
        total = rope.total_sum()
        assert total.charlen == 5  # 4 chars in "café" + 1 emoji
        assert total.bytelen > 5   # Unicode chars take more bytes


class TestSumRopeQuery:
    """Test SumRope query operations."""

    def test_query_basic(self):
        """Test query returns line index and sum values."""
        groups = [RLEGroup("hello\n"), RLEGroup("world\n")]
        rope = SumRope(groups)
        # Query at position 3 in dimension 0 (char dimension)
        line_idx, line_start, position, rle_group, history = rope.query(3, 0)

        assert isinstance(line_idx, int)
        assert isinstance(line_start, LenPair)
        assert isinstance(position, LenPair)
        assert isinstance(rle_group, RLEGroup)
        assert isinstance(history, list)

    def test_query_at_start(self):
        """Test query at position 0."""
        groups = [RLEGroup("hello\n"), RLEGroup("world\n")]
        rope = SumRope(groups)
        line_idx, line_start, position, rle_group, history = rope.query(0, 0)

        assert line_idx == 0
        assert line_start.charlen == 0
        assert line_start.bytelen == 0

    def test_query_byte_index(self):
        """Test query using byte index (index=1)."""
        groups = [RLEGroup("café\n"), RLEGroup("test\n")]
        rope = SumRope(groups)
        # Query by byte offset
        line_idx, line_start, position, rle_group, history = rope.query(5, 1)

        assert isinstance(line_idx, int)
        assert isinstance(position, LenPair)


class TestSumRopeList:
    """Test SumRope list operations."""

    def test_to_list(self):
        """Test to_list returns all values as flattened list."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)
        items = rope.to_list()

        assert isinstance(items, list)
        assert len(items) == 3
        assert all(isinstance(item, RLEGroup) for item in items)


class TestLeafNode:
    """Test LeafNode operations."""

    def test_init(self):
        """Test LeafNode initialization."""
        groups = [RLEGroup("a"), RLEGroup("b")]
        leaf = LeafNode(groups)
        assert len(leaf) == 2

    def test_len(self):
        """Test LeafNode __len__."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        leaf = LeafNode(groups)
        assert len(leaf) == 3

    def test_update(self):
        """Test LeafNode update ensures sum is up to date."""
        groups = [RLEGroup("a"), RLEGroup("b")]
        leaf = LeafNode(groups)
        leaf.update()
        assert isinstance(leaf.sum, LenPair)

    def test_update_rec(self):
        """Test LeafNode update_rec ensures sum is up to date recursively."""
        groups = [RLEGroup("a"), RLEGroup("b")]
        leaf = LeafNode(groups)
        leaf.update_rec()
        assert isinstance(leaf.sum, LenPair)

    def test_flatten(self):
        """Test LeafNode flatten returns all values in one flat list."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        leaf = LeafNode(groups)
        flattened = leaf.flatten()
        assert isinstance(flattened, list)
        assert len(flattened) == 3

    def test_split(self):
        """Test LeafNode split into two leaf nodes at given index."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c"), RLEGroup("d")]
        leaf = LeafNode(groups)
        left, right = leaf.split(2)

        # split should return two nodes (or None if empty)
        assert left is None or isinstance(left, LeafNode)
        assert right is None or isinstance(right, LeafNode)

    def test_query(self):
        """Test LeafNode query returns line index and sum values."""
        groups = [RLEGroup("hello"), RLEGroup("world")]
        leaf = LeafNode(groups)
        history = []
        line_idx, line_start, position, rle_group, new_history = leaf.query(2, 0, history)

        assert isinstance(line_idx, int)
        assert isinstance(line_start, LenPair)
        assert isinstance(position, LenPair)
        assert isinstance(rle_group, RLEGroup)
        assert isinstance(new_history, list)


class TestBranchNode:
    """Test BranchNode operations."""

    def test_init_empty(self):
        """Test BranchNode initialization with no children."""
        branch = BranchNode()
        assert branch.left is None
        assert branch.right is None

    def test_init_with_children(self):
        """Test BranchNode initialization with children."""
        left_leaf = LeafNode([RLEGroup("a")])
        right_leaf = LeafNode([RLEGroup("b")])
        branch = BranchNode(left_leaf, right_leaf)
        assert branch.left is not None
        assert branch.right is not None

    def test_len(self):
        """Test BranchNode __len__."""
        left_leaf = LeafNode([RLEGroup("a"), RLEGroup("b")])
        right_leaf = LeafNode([RLEGroup("c")])
        branch = BranchNode(left_leaf, right_leaf)
        assert len(branch) == 3

    def test_update(self):
        """Test BranchNode update ensures sum is up to date."""
        left_leaf = LeafNode([RLEGroup("a")])
        right_leaf = LeafNode([RLEGroup("b")])
        branch = BranchNode(left_leaf, right_leaf)
        branch.update()
        assert isinstance(branch.sum, LenPair)

    def test_update_rec(self):
        """Test BranchNode update_rec ensures sum is up to date recursively."""
        left_leaf = LeafNode([RLEGroup("a")])
        right_leaf = LeafNode([RLEGroup("b")])
        branch = BranchNode(left_leaf, right_leaf)
        branch.update_rec()
        assert isinstance(branch.sum, LenPair)

    def test_flatten(self):
        """Test BranchNode flatten collects all values under a node."""
        left_leaf = LeafNode([RLEGroup("a"), RLEGroup("b")])
        right_leaf = LeafNode([RLEGroup("c")])
        branch = BranchNode(left_leaf, right_leaf)
        flattened = branch.flatten()
        assert isinstance(flattened, list)
        assert len(flattened) == 3

    def test_split(self):
        """Test BranchNode split into [0:index] and [index:]."""
        left_leaf = LeafNode([RLEGroup("a"), RLEGroup("b")])
        right_leaf = LeafNode([RLEGroup("c"), RLEGroup("d")])
        branch = BranchNode(left_leaf, right_leaf)
        left, right = branch.split(2)

        # Both sides should exist or be None
        assert left is None or isinstance(left, (LeafNode, BranchNode))
        assert right is None or isinstance(right, (LeafNode, BranchNode))

    def test_rebalance(self):
        """Test BranchNode rebalance rebuilds node if too unbalanced."""
        left_leaf = LeafNode([RLEGroup("a")])
        right_leaf = LeafNode([RLEGroup("b")])
        branch = BranchNode(left_leaf, right_leaf)
        result = branch.rebalance()
        # Should return a node (possibly the same one if balanced)
        assert result is None or isinstance(result, (LeafNode, BranchNode))

    def test_query(self):
        """Test BranchNode query returns line index and sum values."""
        left_leaf = LeafNode([RLEGroup("hello")])
        right_leaf = LeafNode([RLEGroup("world")])
        branch = BranchNode(left_leaf, right_leaf)
        history = []
        line_idx, line_start, position, rle_group, new_history = branch.query(2, 0, history)

        assert isinstance(line_idx, int)
        assert isinstance(line_start, LenPair)
        assert isinstance(position, LenPair)
        assert isinstance(rle_group, RLEGroup)
        assert isinstance(new_history, list)


class TestSumRopeComplexScenarios:
    """Test complex scenarios with SumRope."""

    def test_large_rope(self):
        """Test SumRope with many elements."""
        groups = [RLEGroup(f"line{i}\n") for i in range(100)]
        rope = SumRope(groups)
        assert len(rope) == 100
        total = rope.total_sum()
        assert total.charlen > 0
        assert total.bytelen > 0

    def test_multiple_replacements(self):
        """Test performing multiple replace operations."""
        groups = [RLEGroup("a"), RLEGroup("b"), RLEGroup("c")]
        rope = SumRope(groups)

        rope.replace(1, 1, [RLEGroup("x")])
        rope.replace(0, 1, [RLEGroup("y"), RLEGroup("z")])

        assert len(rope) >= 1

    def test_unicode_heavy_content(self):
        """Test SumRope with Unicode-heavy content."""
        groups = [
            RLEGroup("Hello 🌍"),
            RLEGroup("Café ☕"),
            RLEGroup("日本語")
        ]
        rope = SumRope(groups)
        total = rope.total_sum()

        # Chars and bytes should differ significantly
        assert total.charlen > 0
        assert total.bytelen > total.charlen
