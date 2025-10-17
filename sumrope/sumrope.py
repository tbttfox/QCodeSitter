from __future__ import annotations
from typing import Optional, Sequence
from math import log, ceil, floor

# --- Configuration ---
CHUNK_SIZE = 64  # target number of values per leaf
MIN_CHUNK_SIZE = 8
BALANCE_RATIO = 1.5  # acceptable left/right imbalance factor


# --- Core Node Structure ---
class Node:
    __slots__ = ('left', 'right', 'values', 'sum', 'length')

    def __init__(self, values: Optional[list[float]] = None):
        self.left: Optional[Node] = None
        self.right: Optional[Node] = None
        self.values: Optional[list[float]] = values
        self.sum = sum(values) if values else 0.0
        self.length = len(values) if values else 0

    def is_leaf(self) -> bool:
        return self.values is not None

    def recalc(self):
        """Recalculate sum and length from children or values."""
        if self.is_leaf():
            self.sum = sum(self.values)
            self.length = len(self.values)
        else:
            self.sum = (self.left.sum if self.left else 0.0) + (
                self.right.sum if self.right else 0.0
            )
            self.length = (self.left.length if self.left else 0) + (
                self.right.length if self.right else 0
            )


# --- Helpers ---
def _flatten(root) -> list[float]:
    """Collect all values under a node."""
    ret = []
    stack = [root]  # (node, offset of first item in this subtree)

    while stack:
        node = stack.pop()

        if node.is_leaf():
            ret += node.values
        else:
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

    leaves = []
    idx = 0
    for count in counts:
        leaves.append(Node(values[idx : idx + count]))
        idx += count

    while len(leaves) > 1:
        pars = []
        for i in range(0, len(leaves), 2):
            nn = Node()
            nn.left = leaves[i]
            if i + 1 < len(leaves):
                nn.right = leaves[i + 1]
            nn.recalc()
            pars.append(nn)
        leaves = pars

    assert len(leaves) == 1
    return leaves[0]  # The root node


def _rebalance(node: Optional[Node]) -> Optional[Node]:
    """Rebuild the node if it's too unbalanced."""
    if not node or node.is_leaf():
        return node
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
    node = Node()
    node.left, node.right = a, b
    node.values = None
    node.recalc()
    return _rebalance(node)


def _split(node: Optional[Node], index: int) -> tuple[Optional[Node], Optional[Node]]:
    """Split the tree into [0:index] and [index:]."""
    if not node:
        return None, None
    if node.is_leaf():
        left_vals = node.values[:index]
        right_vals = node.values[index:]
        left = Node(left_vals) if left_vals else None
        right = Node(right_vals) if right_vals else None
        return left, right

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

        while not node.is_leaf() and node is not None:
            if index < node.left.length if node.left else 0:
                node = node.left
            else:
                index -= node.left.length if node.left else 0
                node = node.right

        if node is None:
            raise IndexError("SumRope could not find Index")

        return node.values[index]

    def get_range(self, start, end) -> list[float]:
        """
        Yield items from leaf nodes in the tree from index `start` to `end` (exclusive),
        without recursion. Assumes leaf nodes have a list of items and node.is_leaf().

        start and end are absolute indices over the flattened items.
        """
        root = self.root
        if start < 0:
            start = root.length + start
        if end < 0:
            end = root.length + end

        ret = []
        stack = [(root, 0, root.length)]  # (node, offset of first item in this subtree)

        while stack:
            node, nstart, nend = stack.pop()
            if not (nstart < end and nend > start):
                continue

            if node.is_leaf():
                ret += node.values[max(nstart, start) : min(nend, end)]
            else:
                # Push right first so left is processed first (pre-order DFS)
                if node.right and node.right.length:
                    stack.append((node.right, end - node.right.length, end))
                if node.left and node.left.length:
                    stack.append((node.left, start, start + node.left.length))
        return ret

    def prefix_sum(self, index):
        """Sum of items [0: index)"""
        node = self.root
        if index >= node.length + 1:
            raise IndexError("SumRope index out of range")

        if index == 0:
            return 0
        elif index < 0:
            index = node.length + index

        total = 0
        while not node.is_leaf():
            if index < node.left.length:
                node = node.left
            else:
                index -= node.left.length
                total += node.left.sum
                node = node.right

        return total + sum(node.values[:index])

    def range_sum(self, start: int, end: int) -> float:
        """Return sum of values in [start:end)."""
        return self.prefix_sum(end) - self.prefix_sum(start)

    def total_sum(self) -> float:
        """Return sum of all values."""
        return self.root.sum if self.root else 0.0

    def to_list(self) -> list[float]:
        """Return all values as a flattened list"""
        return _flatten(self.root)
