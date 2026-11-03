"""Text predicates for tree-sitter queries

Tree-sitter's built-in text predicates (#eq?, #match?, #any-of?, etc) compare the
node's source text against the strings in the query. Our trees are parsed as UTF-16,
so tree-sitter compares UTF-16 bytes against UTF-8 strings, and they never match.

To get around this, `prepare_query_source` renames the text predicates so tree-sitter
treats them as custom predicates, and `QueryPredicates` evaluates them against the
node text it is given, which TrackedDocument.node_text reads from the document.
"""

from __future__ import annotations

import functools
import re
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node

    from . import Captures, PredicateArgs


PREFIX = "qcs-"
_TEXT_PREDICATE_RE = re.compile(r"#((?:not-)?(?:eq|match|lua-match|any-of))\?")

# Lua pattern character classes (nvim queries use these) as regex set contents
_LUA_CLASSES = {
    "a": r"A-Za-z",
    "c": r"\x00-\x1f\x7f",
    "d": r"0-9",
    "l": r"a-z",
    "p": r"!-/:-@\[-`{-~",
    "s": r"\s",
    "u": r"A-Z",
    "w": r"A-Za-z0-9",
    "x": r"A-Fa-f0-9",
}


def prepare_query_source(source: str) -> str:
    """Rename the text predicates in a query so we can evaluate them ourselves"""
    return _TEXT_PREDICATE_RE.sub(lambda m: f"#{PREFIX}{m.group(1)}?", source)


def _lua_class(nxt: str, in_set: bool) -> str:
    """Convert the character after a % into regex"""
    cls = _LUA_CLASSES.get(nxt.lower())
    if cls is None:
        # %% or %. etc are escaped literals
        return re.escape(nxt)
    if not nxt.isupper():
        return cls if in_set else f"[{cls}]"
    # Uppercase classes are the complement
    if in_set:
        raise re.error(f"%{nxt} is not supported inside a set")
    return f"[^{cls}]"


def lua_to_regex(pattern: str) -> str:
    """Convert the lua pattern character classes (ie %u, %l) into a python regex

    Only handles the character classes, which is what the nvim queries use.
    Normal regex syntax passes through unchanged. The complement classes (ie %U)
    aren't supported inside of a [set]
    """
    out = []
    in_set = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch in "%\\" and i + 1 < len(pattern):
            pair = pattern[i : i + 2]
            out.append(_lua_class(pair[1], in_set) if ch == "%" else pair)
            i += 2
            continue
        if ch == "[" and not in_set:
            in_set = True
        elif ch == "]" and in_set:
            in_set = False
        out.append(ch)
        i += 1
    return "".join(out)


@functools.lru_cache(maxsize=256)
def _compile_pattern(pattern: str) -> re.Pattern | None:
    """Compile a #match? pattern once, or warn once and give None if it's invalid"""
    try:
        return re.compile(lua_to_regex(pattern))
    except re.error as err:
        warnings.warn(
            f"Invalid #match? pattern {pattern!r} in a tree-sitter query: {err}",
            stacklevel=2,
        )
        return None


class QueryPredicates:
    """A predicate callback for QueryCursor.captures that evaluates the renamed
    text predicates using the text from a document

    Args:
        get_text: A function that returns the source text of a node
    """

    def __init__(self, get_text: Callable[[Node], str]) -> None:
        self.get_text = get_text

    def _eq_check(
        self, rest: PredicateArgs, captures: Captures
    ) -> Callable[[str], bool] | None:
        value, kind = rest[0]
        if kind != "capture":
            return lambda text: text == value
        others = captures.get(value, [])
        if not others:
            return None
        other = self.get_text(others[0])
        return lambda text: text == other

    def _match_check(self, rest: PredicateArgs) -> Callable[[str], bool]:
        regex = _compile_pattern(rest[0][0])
        if regex is None:
            # An invalid pattern can't match anything
            return lambda _text: False
        return lambda text: regex.search(text) is not None

    def _make_check(
        self, name: str, rest: PredicateArgs, captures: Captures
    ) -> Callable[[str], bool] | None:
        """Build the text test for a predicate, or None if it can't filter"""
        if name == "any-of":
            values = {value for value, _kind in rest}
            return lambda text: text in values
        if not rest:
            return None
        if name == "eq":
            return self._eq_check(rest, captures)
        # The nvim queries use lua classes in #match? too, so treat them the same
        if name in ("match", "lua-match"):
            return self._match_check(rest)
        return None

    def __call__(
        self,
        predicate: str,
        args: PredicateArgs,
        pattern_index: int,
        captures: Captures,
    ) -> bool:
        # The names match tree-sitter's QueryPredicate protocol
        name = predicate
        if not name.startswith(PREFIX):
            # Not one of ours. Don't filter anything out
            return True
        name = name[len(PREFIX) : -1]
        negate = name.startswith("not-")
        if negate:
            name = name[4:]

        if not args or args[0][1] != "capture":
            return True
        check = self._make_check(name, args[1:], captures)
        if check is None:
            return True
        return all(
            check(self.get_text(node)) != negate
            for node in captures.get(args[0][0], [])
        )
