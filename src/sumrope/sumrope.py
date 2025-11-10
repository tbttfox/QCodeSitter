from __future__ import annotations
from collections.abc import Sequence
from math import log, ceil, floor
from typing import (
    Optional,
    Union,
    cast,
    overload,
)

# --- Configuration ---
CHUNK_SIZE: int = 4  # target number of values per leaf
BALANCE_RATIO: float = 1.5  # acceptable left/right imbalance factor


class IntGroup:
    """A tuple-ish group of integers that can be added and subtracted"""

    __slots__: tuple[str, ...] = ("_group",)
    size = 2

    def __init__(self, group: Optional[Union[list[int], IntGroup]] = None):
        self._group: list[int]
        if group is None:
            self._group = [0] * self.size
        elif isinstance(group, IntGroup):
            self._group = group._group[:]
        else:
            self._group = list(group)

    def __getitem__(self, index: int) -> int:
        return self._group[index]

    def __add__(self, other: IntGroup) -> IntGroup:
        if self.size != other.size:
            raise ValueError("The IntGroup Sizes do not match")
        return IntGroup([a + b for a, b in zip(self._group, other._group)])

    def __sub__(self, other: IntGroup) -> IntGroup:
        if self.size != other.size:
            raise ValueError("The IntGroup Sizes do not match")
        return IntGroup([a - b for a, b in zip(self._group, other._group)])

    def __repr__(self):
        return f"<IntGroup {self._group}>"


class LeafNode:
    __slots__: tuple[str, ...] = ("values", "sum", "_cs")

    def __init__(
        self,
        values: list[IntGroup],
    ):
        self.values: list[IntGroup] = values
        self.sum: IntGroup
        self.update()

    def update(self):
        """Ensure that the sum is up to date"""
        self.update_rec()

    def update_rec(self):
        """Ensure that the sum is up to date, recursively"""
        self.sum = sum(self.values, start=IntGroup())

    def __len__(self):
        return len(self.values)

    def flatten(self) -> list[IntGroup]:
        """Get all of the values in one flat list"""
        return self.values

    def split(self, index: int) -> tuple[Optional[LeafNode], Optional[LeafNode]]:
        """Split the current item into two leaf nodes at the given local index"""
        left_vals = self.values[:index]
        right_vals = self.values[index:]
        left = LeafNode(left_vals) if left_vals else None
        right = LeafNode(right_vals) if right_vals else None
        return left, right

    def get_line_and_offsets_for_sum(
        self, value: int, index: int
    ) -> tuple[int, IntGroup]:
        """Get the line index for the given sum, and the sum values for that index

        Args:
            value: The sum value to find the line index for
            index: The IntPair index to search

        Returns:
            int: The line to insert at
            IntGroup: The sum value of that line. This value just comes along for free
        """
        if value < 0:
            return 0, IntGroup()

        sm = IntGroup()
        for i, v in enumerate(self.values):
            c = sm[index]
            if c <= value and c + v[index] > value:
                return i, sm
            sm += v
        return len(self.values), self.sum


class BranchNode:
    __slots__: tuple[str, ...] = ("left", "right", "sum", "length")

    def __init__(
        self,
        left: ONode = None,
        right: ONode = None,
    ):
        self.left: ONode = left
        self.right: ONode = right
        self.sum: IntGroup
        self.length: int
        self.update()

    def update(self):
        """Ensure that the sum is up to date"""
        leftsum: IntGroup = IntGroup() if self.left is None else self.left.sum
        rightsum: IntGroup = IntGroup() if self.right is None else self.right.sum
        self.sum = leftsum + rightsum

        leftlen: int = 0 if self.left is None else len(self.left)
        rightlen: int = 0 if self.right is None else len(self.right)
        self.length = leftlen + rightlen

    def update_rec(self):
        """Ensure that the sum is up to date, recursively"""
        if self.left is not None:
            self.left.update_rec()
        if self.right is not None:
            self.right.update_rec()
        self.update()

    def __len__(self):
        return self.length

    def rebalance(self) -> ONode:
        """Rebuild the node if it's too unbalanced."""
        # node is a BranchNode
        left_len = len(self.left) if self.left else 0
        right_len = len(self.right) if self.right else 0

        if (left_len * BALANCE_RATIO < right_len) or (
            right_len * BALANCE_RATIO < left_len
        ):
            vals = self.flatten()
            return _build_balanced(vals)
        return self

    def flatten(self) -> list[IntGroup]:
        """Collect all values under a node."""
        flatleft: list[IntGroup] = self.left.flatten() if self.left is not None else []
        flatright: list[IntGroup] = (
            self.right.flatten() if self.right is not None else []
        )
        return flatleft + flatright

    def split(self, index: int) -> tuple[ONode, ONode]:
        """Split the tree into [0:index] and [index:]."""
        # node is a BranchNode
        left_len = len(self.left) if self.left else 0
        if index < left_len:
            if self.left is None:
                return None, None
            left_part, right_part = self.left.split(index)
            new_right = _concat(right_part, self.right)
            return (
                _rebalance(left_part),
                _rebalance(new_right),
            )
        else:
            if self.right is None:
                return None, None
            right_index = index - left_len
            left_part, right_part = self.right.split(right_index)
            new_left = _concat(self.left, left_part)
            return (
                _rebalance(new_left),
                _rebalance(right_part),
            )

    def get_line_and_offsets_for_sum(
        self, value: int, index: int
    ) -> tuple[int, IntGroup]:
        """Get the line index for the given sum, and the sum values for that index

        Args:
            value: The sum value to find the line index for
            index: The IntPair index to search

        Returns:
            int: The line to insert at
            IntGroup: The sum value of that line. This value just comes along for free
        """
        if self.left is None:
            if self.right is None:
                return 0, IntGroup()
            return self.right.get_line_and_offsets_for_sum(value, index)

        if value > self.left.sum[index]:
            if self.right is None:
                return len(self.left), self.left.sum
            loff = self.left.sum[index]
            rlen, roff = self.right.get_line_and_offsets_for_sum(value - loff, index)
            return rlen + len(self.left), roff + self.left.sum
        else:
            return self.left.get_line_and_offsets_for_sum(value, index)


Node = Union[LeafNode, BranchNode]
ONode = Optional[Node]


def _build_balanced(values: list[IntGroup]) -> ONode:
    """Build a perfectly balanced tree."""
    if not values:
        return None

    shift = max(ceil(log(len(values) / CHUNK_SIZE, 2)), 0)
    num_chunks: int = 1 << shift
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
            left = leaves[i]
            right = None if i + 1 >= len(leaves) else leaves[i + 1]
            nn = BranchNode(left, right)
            pars.append(nn)
        leaves = pars

    assert len(leaves) == 1
    return leaves[0]  # The root node


def _rebalance(node: ONode) -> ONode:
    """Rebuild the node if it's too unbalanced."""
    if node is None or isinstance(node, LeafNode):
        return node

    # node is a BranchNode
    left_len = len(node.left) if node.left else 0
    right_len = len(node.right) if node.right else 0

    if (left_len * BALANCE_RATIO < right_len) or (right_len * BALANCE_RATIO < left_len):
        vals = node.flatten()
        return _build_balanced(vals)
    return node


def _concat(a: ONode, b: ONode) -> ONode:
    """Join two trees, rebalancing if necessary."""
    if a is None:
        return b
    if b is None:
        return a
    return BranchNode(a, b)


# --- Main Rope Class ---
class SumRope:
    """Dynamic sequence with efficient cumulative sums and chunk replacements."""

    def __init__(self, values: Sequence[IntGroup] = ()):
        self.root: ONode = _build_balanced(list(values))

    # --- Public API ---
    def __len__(self) -> int:
        return len(self.root) if self.root else 0

    def replace(self, start: int, old_count: int, new_values: Sequence[IntGroup]):
        """Replace old_count values starting at start with new_values."""
        left, tail, right = None, None, None
        if self.root is not None:
            left, tail = self.root.split(start)

        if tail is not None:
            _, right = tail.split(old_count)

        mid = _build_balanced(list(new_values))
        self.root = _rebalance(_concat(_concat(left, mid), right))

    def __getitem__(self, key: Union[int, slice]) -> Union[IntGroup, list[IntGroup]]:
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
    def __setitem__(self, key: int, value: IntGroup) -> None: ...

    @overload
    def __setitem__(self, key: slice, value: Sequence[IntGroup]) -> None: ...

    def __setitem__(
        self, key: Union[int, slice], value: Union[IntGroup, Sequence[IntGroup]]
    ) -> None:
        setval: Sequence[IntGroup]
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step != 1:
                raise ValueError("Slice step must be 1")
            count = stop - start
            setval = cast(Sequence[IntGroup], value)
        else:
            start = key
            count = 1
            if key < 0:
                key += len(self)
            if key < 0 or key >= len(self):
                raise IndexError("Index out of range")
            setval = [cast(IntGroup, value)]

        self.replace(start, count, setval)

    # ------------------------------------------------------------
    # Core access operations
    # ------------------------------------------------------------

    def get_single(self, index: int) -> IntGroup:
        node = self.root
        if node is None:
            raise IndexError("SumRope has no root")

        if index >= len(node):
            raise IndexError("SumRope index out of range")

        while isinstance(node, BranchNode):
            left_len = len(node.left) if node.left else 0
            if index < left_len:
                node = node.left
            else:
                index -= left_len
                node = node.right

        if isinstance(node, LeafNode):
            return node.values[index]

        raise IndexError("SumRope could not find Index")

    def get_range(self, start: int, end: int) -> list[IntGroup]:
        """
        Get items from index `start` to `end` (exclusive).
        Optimized to correctly track node offsets.
        """
        root = self.root
        if not root:
            return []

        if start < 0:
            start = len(root) + start
        if end < 0:
            end = len(root) + end

        # Clamp to valid range
        start = max(0, min(start, len(root)))
        end = max(0, min(end, len(root)))

        if start >= end:
            return []

        ret: list[IntGroup] = []
        stack = [(root, 0)]  # (node, offset_in_sequence)

        while stack:
            node, offset = stack.pop()
            node_end = offset + len(node)

            # Skip if this node doesn't overlap [start, end)
            if node_end <= start or offset >= end:
                continue

            if isinstance(node, LeafNode):
                # Calculate which portion of this leaf we need
                local_start = max(0, start - offset)
                local_end = min(len(node), end - offset)
                ret.extend(node.values[local_start:local_end])
            else:  # BranchNode
                # Push right first so left is processed first (maintains order)
                left_len = len(node.left) if node.left else 0
                if node.right:
                    stack.append((node.right, offset + left_len))
                if node.left:
                    stack.append((node.left, offset))

        return ret

    def prefix_sum(self, index: int) -> IntGroup:
        """Sum of items [0: index)"""
        node = self.root
        if node is None:
            raise ValueError("No data in node")
        if index >= len(node) + 1:
            raise IndexError("SumRope index out of range")

        if index == 0:
            return IntGroup()

        elif index < 0:
            index = len(node) + index

        total = IntGroup()
        while isinstance(node, BranchNode):
            left_len = len(node.left) if node.left else 0
            left_sum = node.left.sum if node.left else IntGroup()
            if index < left_len:
                node = node.left
            else:
                index -= left_len
                total = total + left_sum
                node = node.right

        if isinstance(node, LeafNode):
            return total + sum(node.values[:index], start=IntGroup())

        return total

    def range_sum(self, start: int, end: int) -> IntGroup:
        """Return sum of values in [start:end)."""
        return self.prefix_sum(end) - self.prefix_sum(start)

    def total_sum(self) -> IntGroup:
        """Return sum of all values."""
        return self.root.sum if self.root else IntGroup()

    def to_list(self) -> list[IntGroup]:
        """Return all values as a flattened list"""
        if self.root is None:
            return []
        return self.root.flatten()

    def get_line_and_offsets_for_sum(
        self, value: int, index: int
    ) -> tuple[int, IntGroup]:
        """Get the line index for the given sum, and the sum values for that index

        Args:
            value: The sum value to find the line index for
            index: The IntPair index to search

        Returns:
            int: The line to insert at
            IntGroup: The sum value of that line. This value just comes along for free
        """
        if self.root is None:
            return 0, IntGroup()
        return self.root.get_line_and_offsets_for_sum(value, index)
