"""Compiling and running tree-sitter queries

Every query is compiled with `compile_query` and run with `query_byte_range`.
The text predicates that the highlight queries use are in predicates.py
"""

from __future__ import annotations

import functools
import warnings
from collections.abc import Callable

from tree_sitter import Language, Node, Query, QueryCursor, QueryError

# A predicate argument is (value, "capture" or "string")
PredicateArgs = list[tuple[str, str]]
# Capture name -> the nodes it captured
Captures = dict[str, list[Node]]
# Called with (predicate name, args, pattern index, captures) to filter a match
QueryPredicate = Callable[[str, PredicateArgs, int, Captures], bool]


@functools.lru_cache(maxsize=64)
def compile_query(language: Language, source: str) -> Query | None:
    """Compile a query once, and share it between every editor and behavior

    A query with an error warns once, and gives None so the behavior that
    uses it does nothing, like an invalid #match? pattern matches nothing
    """
    try:
        return Query(language, source)
    except QueryError as err:
        warnings.warn(
            f"Invalid tree-sitter query for {language.name}: {err}", stacklevel=2
        )
        return None


def query_byte_range(
    query: Query,
    root: Node,
    start_byte: int,
    end_byte: int,
    predicate: QueryPredicate | None = None,
) -> Captures:
    """Run a query over a byte range of a tree, returning nodes by capture name

    A query that fails returns no captures and warns. Like a query with an
    error, the same failure only warns once
    """
    cursor = QueryCursor(query)
    try:
        cursor.set_byte_range(start_byte, end_byte)
        if predicate is None:
            # Tree-sitter doesn't accept predicate=None
            return cursor.captures(root)
        return cursor.captures(root, predicate=predicate)
    except (ValueError, RuntimeError) as err:
        warnings.warn(f"A tree-sitter query failed to run: {err!r}", stacklevel=2)
        return {}
