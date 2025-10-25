from __future__ import annotations
from typing import Optional, Sequence, Union
from math import log, ceil, floor

# --- Configuration ---
CHUNK_SIZE = 64  # target number of values per leaf
BALANCE_RATIO = 1.5  # acceptable left/right imbalance factor


# --- Core Node Structure ---
class LeafNode:
    __slots__ = ("values", "sum", "length")

    def __init__(self, values: list[float]):
        self.values: list[float] = values
        self.sum = sum(values)
        self.length = len(values)


class BranchNode:
    __slots__ = ("left", "right", "sum", "length")

    def __init__(self, left: Optional[Node] = None, right: Optional[Node] = None):
        self.left: Optional[Node] = left
        self.right: Optional[Node] = right
        self.sum = 0.0
        self.length = 0


Node = Union[LeafNode, BranchNode]


def recalc(node: BranchNode):
    """Recalculate sum and length from children."""
    node.sum = (node.left.sum if node.left else 0.0) + (
        node.right.sum if node.right else 0.0
    )
    node.length = (node.left.length if node.left else 0) + (
        node.right.length if node.right else 0
    )


# --- Helpers ---
def _flatten(root: Optional[Node]) -> list[float]:
    """Collect all values under a node."""
    if not root:
        return []

    ret = []
    stack = [root]

    while stack:
        node = stack.pop()

        if isinstance(node, LeafNode):
            ret += node.values
        else:  # BranchNode
            # Push right first so left is processed first (pre-order DFS)
            if node.right:
                stack.append(node.right)
            if node.left:
                stack.append(node.left)
    return ret


def _build_balanced(values: list[float]) -> Optional[Node]:
    """Build a perfectly balanced tree."""
    if not values:
        return None

    num_chunks = 2 ** ceil(log(len(values) / CHUNK_SIZE, 2))
    if num_chunks < 1:
        counts = [len(values)]
    else:
        ideal_size = len(values) / num_chunks
        ceil_count = len(values) - (floor(ideal_size) * num_chunks)
        floor_count = num_chunks - ceil_count
        counts = [ceil(ideal_size)] * ceil_count + [floor(ideal_size)] * floor_count

    leaves: list[Node] = []
    idx = 0
    for count in counts:
        leaves.append(LeafNode(values[idx : idx + count]))
        idx += count

    while len(leaves) > 1:
        pars: list[Node] = []
        for i in range(0, len(leaves), 2):
            nn = BranchNode()
            nn.left = leaves[i]
            if i + 1 < len(leaves):
                nn.right = leaves[i + 1]
            recalc(nn)
            pars.append(nn)
        leaves = pars

    assert len(leaves) == 1
    return leaves[0]  # The root node


def _rebalance(node: Optional[Node]) -> Optional[Node]:
    """Rebuild the node if it's too unbalanced."""
    if not node or isinstance(node, LeafNode):
        return node

    # node is a BranchNode
    left_len = node.left.length if node.left else 0
    right_len = node.right.length if node.right else 0

    if (left_len * BALANCE_RATIO < right_len) or (right_len * BALANCE_RATIO < left_len):
        vals = _flatten(node)
        return _build_balanced(vals)
    return node


def _concat(a: Optional[Node], b: Optional[Node]) -> Optional[Node]:
    """Join two trees, rebalancing if necessary."""
    if not a:
        return b
    if not b:
        return a
    node = BranchNode(a, b)
    recalc(node)
    return _rebalance(node)


def _split(node: Optional[Node], index: int) -> tuple[Optional[Node], Optional[Node]]:
    """Split the tree into [0:index] and [index:]."""
    if not node:
        return None, None

    if isinstance(node, LeafNode):
        left_vals = node.values[:index]
        right_vals = node.values[index:]
        left = LeafNode(left_vals) if left_vals else None
        right = LeafNode(right_vals) if right_vals else None
        return left, right

    # node is a BranchNode
    left_len = node.left.length if node.left else 0
    if index < left_len:
        left_part, right_part = _split(node.left, index)
        new_right = _concat(right_part, node.right)
        return _rebalance(left_part), _rebalance(new_right)
    else:
        right_index = index - left_len
        left_part, right_part = _split(node.right, right_index)
        new_left = _concat(node.left, left_part)
        return _rebalance(new_left), _rebalance(right_part)


# --- Main Rope Class ---
class SumRope:
    """Dynamic sequence with efficient cumulative sums and chunk replacements."""

    def __init__(self, values: Sequence[float] = ()):
        self.root = _build_balanced(list(values))

    # --- Internal helpers ---
    @staticmethod
    def _build(values: list[float]) -> Optional[Node]:
        return _build_balanced(values)

    # --- Public API ---
    def __len__(self) -> int:
        return self.root.length if self.root else 0

    def replace(self, start: int, old_count: int, new_values: Sequence[float]):
        """Replace old_count values starting at start with new_values."""
        left, tail = _split(self.root, start)
        _, right = _split(tail, old_count)
        mid = _build_balanced(list(new_values))
        self.root = _concat(_concat(left, mid), right)

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step != 1:
                raise ValueError("Slice step must be 1")
            return self.get_range(start, stop)
        else:
            if key < 0:
                key += len(self)
            if key < 0 or key >= len(self):
                raise IndexError("Index out of range")
            return self.get_single(key)

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step != 1:
                raise ValueError("Slice step must be 1")
            self.replace(start, stop - start, value)
        else:
            if key < 0:
                key += len(self)
            if key < 0 or key >= len(self):
                raise IndexError("Index out of range")
            self.replace(key, 1, [value])

    # ------------------------------------------------------------
    # Core access operations
    # ------------------------------------------------------------

    def get_single(self, index: int) -> float:
        node = self.root
        if node is None:
            raise IndexError("SumRope has no root")

        if index >= node.length:
            raise IndexError("SumRope index out of range")

        while isinstance(node, BranchNode):
            left_len = node.left.length if node.left else 0
            if index < left_len:
                node = node.left
            else:
                index -= left_len
                node = node.right

        if isinstance(node, LeafNode):
            return node.values[index]

        raise IndexError("SumRope could not find Index")


    def get_range(self, start, end) -> list[float]:
        """
        Get items from index `start` to `end` (exclusive).
        Optimized to correctly track node offsets.
        """
        root = self.root
        if not root:
            return []

        if start < 0:
            start = root.length + start
        if end < 0:
            end = root.length + end

        # Clamp to valid range
        start = max(0, min(start, root.length))
        end = max(0, min(end, root.length))

        if start >= end:
            return []

        ret = []
        stack = [(root, 0)]  # (node, offset_in_sequence)

        while stack:
            node, offset = stack.pop()
            node_end = offset + node.length

            # Skip if this node doesn't overlap [start, end)
            if node_end <= start or offset >= end:
                continue

            if isinstance(node, LeafNode):
                # Calculate which portion of this leaf we need
                local_start = max(0, start - offset)
                local_end = min(node.length, end - offset)
                ret.extend(node.values[local_start:local_end])
            else:  # BranchNode
                # Push right first so left is processed first (maintains order)
                left_len = node.left.length if node.left else 0
                if node.right:
                    stack.append((node.right, offset + left_len))
                if node.left:
                    stack.append((node.left, offset))

        return ret

    def prefix_sum(self, index):
        """Sum of items [0: index)"""
        node = self.root
        if node is None:
            raise ValueError("No data in node")
        if index >= node.length + 1:
            raise IndexError("SumRope index out of range")

        if index == 0:
            return 0
        elif index < 0:
            index = node.length + index

        total = 0
        while isinstance(node, BranchNode):
            left_len = node.left.length if node.left else 0
            left_sum = node.left.sum if node.left else 0.0
            if index < left_len:
                node = node.left
            else:
                index -= left_len
                total += left_sum
                node = node.right

        if isinstance(node, LeafNode):
            return total + sum(node.values[:index])

        return total

    def range_sum(self, start: int, end: int) -> float:
        """Return sum of values in [start:end)."""
        return self.prefix_sum(end) - self.prefix_sum(start)

    def total_sum(self) -> float:
        """Return sum of all values."""
        return self.root.sum if self.root else 0.0

    def to_list(self) -> list[float]:
        """Return all values as a flattened list"""
        return _flatten(self.root)
