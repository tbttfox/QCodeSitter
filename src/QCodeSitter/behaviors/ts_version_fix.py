from __future__ import annotations
from tree_sitter import Query
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tree_sitter import Node

try:
    # Tree_sitter_python version > 23
    # Python 3.10+
    from tree_sitter import QueryCursor

    def query_byte_range(
        query: Query, root: Node, start_byte: int, end_byte: int
    ) -> Optional[dict[str, list[Node]]]:
        try:
            cursor = QueryCursor(query)
            cursor.set_byte_range(start_byte, end_byte)
            return cursor.captures(root)
        except (ValueError, RuntimeError):
            # Query failed - tree might be in inconsistent state
            return None

except ImportError:
    # Tree_sitter_python version == 23
    # Python 3.9
    def query_byte_range(
        query: Query, root: Node, start_byte: int, end_byte: int
    ) -> Optional[dict[str, list[Node]]]:
        try:
            query.set_byte_range((start_byte, end_byte))
            return query.captures(root)
        except (ValueError, RuntimeError):
            # Query failed - tree might be in inconsistent state
            return None
