"""Compiling and running tree-sitter queries

Every query is compiled with `compile_query` and run with `query_byte_range`.
The text predicates that the highlight queries use are in predicates.py
"""

from __future__ import annotations

import functools
import logging
import warnings
from collections.abc import Callable

from tree_sitter import Language, Node, Query, QueryCursor, QueryError

logger = logging.getLogger(__name__)

# A predicate argument is (value, "capture" or "string")
PredicateArgs = list[tuple[str, str]]
# Capture name -> the nodes it captured
Captures = dict[str, list[Node]]
# Called with (predicate name, args, pattern index, captures) to filter a match
QueryPredicate = Callable[[str, PredicateArgs, int, Captures], bool]

# The queries that failed to run, so each one is only logged as a warning once
_failed_queries: set[Query] = set()


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

    A query that fails returns no captures. The first failure of each query is
    logged as a warning, and the rest at debug level
    """
    cursor = QueryCursor(query)
    try:
        cursor.set_byte_range(start_byte, end_byte)
        if predicate is None:
            # Tree-sitter doesn't accept predicate=None
            return cursor.captures(root)
        return cursor.captures(root, predicate=predicate)
    except (ValueError, RuntimeError):
        first_failure = query not in _failed_queries
        _failed_queries.add(query)
        logger.log(
            logging.WARNING if first_failure else logging.DEBUG,
            "Query failed over bytes %d-%d",
            start_byte,
            end_byte,
            exc_info=True,
        )
        return {}
