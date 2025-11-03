from __future__ import annotations
from collections.abc import Sequence
from math import log, ceil, floor
from typing import TypeVar, Callable, Generic, overload, cast
from functools import reduce

# --- Configuration ---
CHUNK_SIZE: int = 64  # target number of values per leaf
BALANCE_RATIO: float = 1.5  # acceptable left/right imbalance factor


T = TypeVar("T")
S = Callable[[T | None, T | None], T]
N = Callable[[T], T]


class LeafNode(Generic[T]):
    __slots__: tuple[str, ...] = ("values", "sum", "length", "sumfunc")

    def __init__(
        self,
        sumfunc: S[T],
        values: list[T],
    ):
        self.values: list[T] = values
        self.sumfunc: S[T] = sumfunc
        self.sum: T = reduce(self.sumfunc, values)
        self.length: int = len(values)

    def flatten(self) -> list[T]:
        return self.values

    def split(self, index: int) -> tuple[LeafNode[T] | None, LeafNode[T] | None]:
        left_vals = self.values[:index]
        right_vals = self.values[index:]
        left = LeafNode(self.sumfunc, left_vals) if left_vals else None
        right = LeafNode(self.sumfunc, right_vals) if right_vals else None
        return left, right


class BranchNode(Generic[T]):
    __slots__: tuple[str, ...] = ("left", "right", "sum", "length", "sumfunc")

    def __init__(
        self,
        sumfunc: S[T],
        left: Node[T] | None = None,
        right: Node[T] | None = None,
    ):
        self.left: Node[T] | None = left
        self.right: Node[T] | None = right
        self.sumfunc: S[T] = sumfunc
        leftsum = self.left.sum if self.left else None
        rightsum = self.right.sum if self.right else None
        self.sum: T = self.sumfunc(leftsum, rightsum)
        self.length: int = 0

    def rebalance(self) -> Node[T] | None:
        """Rebuild the node if it's too unbalanced."""
        # node is a BranchNode
        left_len = self.left.length if self.left else 0
        right_len = self.right.length if self.right else 0

        if (left_len * BALANCE_RATIO < right_len) or (
            right_len * BALANCE_RATIO < left_len
        ):
            vals = self.flatten()
            return _build_balanced(self.sumfunc, vals)
        return self

    def flatten(self) -> list[T]:
        """Collect all values under a node."""
        flatleft: list[T] = self.left.flatten() if self.left is not None else []
        flatright: list[T] = self.right.flatten() if self.right is not None else []
        return flatleft + flatright

    def split(self, index: int) -> tuple[Node[T] | None, Node[T] | None]:
        """Split the tree into [0:index] and [index:]."""
        # node is a BranchNode
        left_len = self.left.length if self.left else 0
        if index < left_len:
            if self.left is None:
                return None, None
            left_part, right_part = self.left.split(index)
            new_right = _concat(right_part, self.right)
            return (
                _rebalance(self.sumfunc, left_part),
                _rebalance(self.sumfunc, new_right),
            )
        else:
            if self.right is None:
                return None, None
            right_index = index - left_len
            left_part, right_part = self.right.split(right_index)
            new_left = _concat(self.left, left_part)
            return (
                _rebalance(self.sumfunc, new_left),
                _rebalance(self.sumfunc, right_part),
            )


Node = LeafNode[T] | BranchNode[T]


def _build_balanced(sumfunc: S[T], values: list[T]) -> Node[T] | None:
    """Build a perfectly balanced tree."""
    if not values:
        return None

    # 1 << x is 2 ** x but for integers
    num_chunks: int = 1 << ceil(log(len(values) / CHUNK_SIZE, 2))

    if num_chunks < 1:
        counts = [len(values)]
    else:
        ideal_size = len(values) / num_chunks
        ceil_count = len(values) - (floor(ideal_size) * num_chunks)
        floor_count = num_chunks - ceil_count
        counts = [ceil(ideal_size)] * ceil_count + [floor(ideal_size)] * floor_count

    leaves: list[Node[T]] = []
    idx = 0
    for count in counts:
        leaves.append(LeafNode(sumfunc, values[idx : idx + count]))
        idx += count

    while len(leaves) > 1:
        pars: list[Node[T]] = []
        for i in range(0, len(leaves), 2):
            left = leaves[i]
            right = None if i + 1 >= len(leaves) else leaves[i + 1]
            nn = BranchNode(sumfunc, left, right)
            pars.append(nn)
        leaves = pars

    assert len(leaves) == 1
    return leaves[0]  # The root node


def _rebalance(sumfunc: S[T], node: Node[T] | None) -> Node[T] | None:
    """Rebuild the node if it's too unbalanced."""
    if not node or isinstance(node, LeafNode):
        return node

    # node is a BranchNode
    left_len = node.left.length if node.left else 0
    right_len = node.right.length if node.right else 0

    if (left_len * BALANCE_RATIO < right_len) or (right_len * BALANCE_RATIO < left_len):
        vals = node.flatten()
        return _build_balanced(sumfunc, vals)
    return node


def _concat(a: Node[T] | None, b: Node[T] | None) -> Node[T] | None:
    """Join two trees, rebalancing if necessary."""
    if not a:
        return b
    if not b:
        return a
    node = BranchNode(a.sumfunc, a, b)
    return _rebalance(a.sumfunc, node)


# --- Main Rope Class ---
class SumRope(Generic[T]):
    """Dynamic sequence with efficient cumulative sums and chunk replacements."""

    def __init__(
        self, sumfunc: S[T], negfunc: N[T], zeroval: T, values: Sequence[T] = ()
    ):
        self.sumfunc: S[T] = sumfunc
        self.negfunc: N[T] = negfunc
        self.zeroval: T = zeroval
        self.root: Node[T] | None = _build_balanced(sumfunc, list(values))

    # --- Public API ---
    def __len__(self) -> int:
        return self.root.length if self.root else 0

    def replace(self, start: int, old_count: int, new_values: Sequence[T]):
        """Replace old_count values starting at start with new_values."""
        left, tail, right = None, None, None
        if self.root is not None:
            left, tail = self.root.split(start)

        if tail is not None:
            _, right = tail.split(old_count)

        mid = _build_balanced(self.sumfunc, list(new_values))
        self.root = _concat(_concat(left, mid), right)

    def __getitem__(self, key: int | slice) -> T | list[T]:
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

    @overload
    def __setitem__(self, key: int, value: T) -> None: ...

    @overload
    def __setitem__(self, key: slice, value: Sequence[T]) -> None: ...

    def __setitem__(self, key: int | slice, value: T | Sequence[T]) -> None:
        setval: Sequence[T]
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step != 1:
                raise ValueError("Slice step must be 1")
            count = stop - start
            setval = cast(Sequence[T], value)
        else:
            start = key
            count = 1
            if key < 0:
                key += len(self)
            if key < 0 or key >= len(self):
                raise IndexError("Index out of range")
            setval = [cast(T, value)]

        self.replace(start, count, setval)

    # ------------------------------------------------------------
    # Core access operations
    # ------------------------------------------------------------

    def get_single(self, index: int) -> T:
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

    def get_range(self, start: int, end: int) -> list[T]:
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

        ret: list[T] = []
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

    def prefix_sum(self, index: int) -> T:
        """Sum of items [0: index)"""
        node = self.root
        if node is None:
            raise ValueError("No data in node")
        if index >= node.length + 1:
            raise IndexError("SumRope index out of range")

        if index == 0:
            return self.zeroval

        elif index < 0:
            index = node.length + index

        total = self.sumfunc(None, None)
        while isinstance(node, BranchNode):
            left_len = node.left.length if node.left else 0
            left_sum = node.left.sum if node.left else self.zeroval
            if index < left_len:
                node = node.left
            else:
                index -= left_len
                total = self.sumfunc(total, left_sum)
                node = node.right

        if isinstance(node, LeafNode):
            return self.sumfunc(total, reduce(self.sumfunc, node.values[:index]))

        return total

    def range_sum(self, start: int, end: int) -> T:
        """Return sum of values in [start:end)."""
        return self.sumfunc(self.prefix_sum(end), self.negfunc(self.prefix_sum(start)))

    def total_sum(self) -> T:
        """Return sum of all values."""
        return self.root.sum if self.root else self.zeroval

    def to_list(self) -> list[T]:
        """Return all values as a flattened list"""
        if self.root is None:
            return []
        return self.root.flatten()
