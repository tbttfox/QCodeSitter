import re
from collections.abc import Sequence
from typing import overload

CHUNK_SIZE: int
BALANCE_RATIO: float

class LenPair:
    """A tuple-ish group of integers that can be added and subtracted"""
    charlen: int
    bytelen: int
    def __init__(self, group: list[int] | LenPair | None = None) -> None: ...
    def __getitem__(self, index: int) -> int: ...
    def __add__(self, other: LenPair) -> LenPair: ...
    def __sub__(self, other: LenPair) -> LenPair: ...

class RLEGroup(LenPair):
    """A tuple-ish group of integers that can be added and subtracted that keeps
    track of each character's length in bytes (RLE encoded)
    """
    encoding: str
    pattern: re.Pattern
    rle: list[tuple[int, int]]
    charlen: int
    bytelen: int
    def __init__(self, txt: str | None = None) -> None: ...
    def byte_to_char(self, b: int) -> int:
        """Convert a local byte offset into a character offset"""
    def char_to_byte(self, c: int) -> int:
        """Convert a local character offset into a byte offset"""
    def byte_to_pair(self, b: int) -> LenPair: ...
    def char_to_pair(self, c: int) -> LenPair: ...

class LeafNode:
    values: list[RLEGroup]
    sum: LenPair
    def __init__(self, values: list[RLEGroup]) -> None: ...
    def update(self) -> None:
        """Ensure that the sum is up to date"""
    def update_rec(self) -> None:
        """Ensure that the sum is up to date, recursively"""
    def __len__(self) -> int: ...
    def flatten(self) -> list[RLEGroup]:
        """Get all of the values in one flat list"""
    def split(self, index: int) -> tuple[LeafNode | None, LeafNode | None]:
        """Split the current item into two leaf nodes at the given local index"""
    def query(self, value: int, index: int, history: list[Node]) -> tuple[int, LenPair, LenPair, RLEGroup, list[Node]]:
        """Get the line index for the given sum, and the sum values for that index

        Args:
            value: The sum value to find the line index for
            index: The IntPair index to search

        Returns:
            int: The line to insert at
            LenPair: The char and byte offsets for the beginning of the line
            LenPair: The char and byte offsets at the given position
            RLEGroup: The rle character group it would be inserted into
            list[Node]: The node history getting to the Leaf with the RLEGroup
        """

class BranchNode:
    left: ONode
    right: ONode
    sum: LenPair
    length: int
    def __init__(self, left: ONode = None, right: ONode = None) -> None: ...
    def update(self) -> None:
        """Ensure that the sum is up to date"""
    def update_rec(self) -> None:
        """Ensure that the sum is up to date, recursively"""
    def __len__(self) -> int: ...
    def rebalance(self) -> ONode:
        """Rebuild the node if it's too unbalanced."""
    def flatten(self) -> list[RLEGroup]:
        """Collect all values under a node."""
    def split(self, index: int) -> tuple[ONode, ONode]:
        """Split the tree into [0:index] and [index:]."""
    def query(self, value: int, index: int, history: list[Node]) -> tuple[int, LenPair, LenPair, RLEGroup, list[Node]]:
        """Get the line index for the given sum, and the sum values for that index

        Args:
            value: The sum value to find the line index for
            index: The IntPair index to search

        Returns:
            int: The line to insert at
            LenPair: The char and byte offsets for the beginning of the line
            LenPair: The char and byte offsets at the given position
            RLEGroup: The rle character group it would be inserted into
            list[Node]: The node history getting to the Leaf with the RLEGroup
        """
Node = LeafNode | BranchNode
ONode = Node | None

class SumRope:
    """Dynamic sequence with efficient cumulative sums and chunk replacements."""
    root: ONode
    def __init__(self, values: Sequence[RLEGroup] = ()) -> None: ...
    @classmethod
    def from_text(cls, txt): ...
    def __len__(self) -> int: ...
    def replace(self, start: int, old_count: int, new_values: Sequence[RLEGroup]):
        """Replace old_count values starting at start with new_values."""
    def __getitem__(self, key: int | slice) -> LenPair | list[LenPair]: ...
    @overload
    def __setitem__(self, key: int, value: RLEGroup) -> None: ...
    @overload
    def __setitem__(self, key: slice, value: Sequence[RLEGroup]) -> None: ...
    def get_single(self, index: int) -> LenPair: ...
    def get_range(self, start: int, end: int) -> list[LenPair]:
        """
        Get items from index `start` to `end` (exclusive).
        Optimized to correctly track node offsets.
        """
    def prefix_sum(self, index: int) -> LenPair:
        """Sum of items [0: index)"""
    def range_sum(self, start: int, end: int) -> LenPair:
        """Return sum of values in [start:end)."""
    def total_sum(self) -> LenPair:
        """Return sum of all values."""
    def to_list(self) -> list[RLEGroup]:
        """Return all values as a flattened list"""
    def query(self, value: int, index: int) -> tuple[int, LenPair, LenPair, RLEGroup, list[Node]]:
        """Get the line index for the given sum, and the sum values for that index

        Args:
            value: The sum value to find the line index for
            index: The IntPair index to search

        Returns:
            int: The line to insert at
            LenPair: The char and byte offsets for the beginning of the line
            LenPair: The char and byte offsets at the given position
            RLEGroup: The rle character group it would be inserted into
            list[Node]: The node history getting to the Leaf with the RLEGroup
        """
