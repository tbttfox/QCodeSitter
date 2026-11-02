"""Compiling and running tree-sitter queries

Every query is compiled with `compile_query` and run with `query_byte_range`.
Tree-sitter can't evaluate text predicates like #eq? on our UTF-16 trees, so
compile_query renames them and query_byte_range evaluates them against the
document text. predicates.py has the details
"""

from __future__ import annotations

import functools
import warnings
from collections.abc import Callable
from typing import Literal

from tree_sitter import Language, Node, Query, QueryCursor, QueryError

from .predicates import QueryPredicates, prepare_query_source

# A predicate argument is (value, "capture" or "string")
PredicateArgs = list[tuple[str, Literal["capture", "string"]]]
# Capture name -> the nodes it captured
Captures = dict[str, list[Node]]


@functools.lru_cache(maxsize=64)
def compile_query(language: Language, source: str) -> Query | None:
    """Compile a query once, and share it between every editor and behavior

    A query with an error warns once, and gives None so the behavior that
    uses it does nothing, like an invalid #match? pattern matches nothing
    """
    try:
        return Query(language, prepare_query_source(source))
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
    get_text: Callable[[Node], str] | None = None,
) -> Captures:
    """Run a query over a byte range of a tree, returning nodes by capture name

    A byte range that ends before it starts warns once and returns no
    captures.

    Args:
        get_text: Returns a node's source text, to evaluate the query's text
            predicates with. Without it, the text predicates match everything.
            Errors it raises propagate
    """
    cursor = QueryCursor(query)
    try:
        cursor.set_byte_range(start_byte, end_byte)
    except ValueError:
        # Tree-sitter rejects a range that ends before it starts
        warnings.warn(
            f"Skipped a tree-sitter query over the reversed byte range "
            f"{start_byte}..{end_byte}",
            stacklevel=2,
        )
        return {}
    if get_text is None:
        # Tree-sitter doesn't accept predicate=None
        return cursor.captures(root)
    return cursor.captures(root, QueryPredicates(get_text))
