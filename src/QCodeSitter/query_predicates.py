"""Text predicates for tree-sitter queries

Tree-sitter's built-in text predicates (#eq?, #match?, #any-of?, etc) compare the
node's source text against the strings in the query. Our trees are parsed with a
callback in UTF-16, so the tree has no source text, and those predicates never match.

To get around this, `prepare_query_source` renames the text predicates so tree-sitter
treats them as custom predicates, and `QueryPredicates` evaluates them by reading
the node text straight out of the QTextDocument.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from .constants import ENC

if TYPE_CHECKING:
    from Qt import QtGui
    from tree_sitter import Node


PREFIX = "qcs-"
_TEXT_PREDICATE_RE = re.compile(
    r"#((?:not-)?(?:eq|match|lua-match|any-of))\?"
)

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
        if ch == "%" and i + 1 < len(pattern):
            nxt = pattern[i + 1]
            cls = _LUA_CLASSES.get(nxt.lower())
            if cls is None:
                # %% or %. etc are escaped literals
                out.append(re.escape(nxt))
            elif nxt.isupper():
                # Uppercase classes are the complement
                if in_set:
                    raise re.error(f"%{nxt} is not supported inside a set")
                out.append(f"[^{cls}]")
            else:
                out.append(cls if in_set else f"[{cls}]")
            i += 2
            continue
        if ch == "\\" and i + 1 < len(pattern):
            out.append(pattern[i : i + 2])
            i += 2
            continue
        if ch == "[" and not in_set:
            in_set = True
        elif ch == "]" and in_set:
            in_set = False
        out.append(ch)
        i += 1
    return "".join(out)


def document_node_text(document: QtGui.QTextDocument, node: Node) -> str:
    """Get the text of a node from a document parsed as UTF-16"""
    start, end = node.start_point, node.end_point
    if start.row == end.row:
        block = document.findBlockByNumber(start.row)
        data = block.text().encode(ENC)
        return data[start.column : end.column].decode(ENC, errors="replace")

    lines = []
    block = document.findBlockByNumber(start.row)
    for row in range(start.row, end.row + 1):
        if not block.isValid():
            break
        data = block.text().encode(ENC)
        first = start.column if row == start.row else 0
        if row == end.row:
            lines.append(data[first : end.column].decode(ENC, errors="replace"))
        else:
            lines.append(data[first:].decode(ENC, errors="replace"))
        block = block.next()
    return "\n".join(lines)


class QueryPredicates:
    """A predicate callback for QueryCursor.captures that evaluates the renamed
    text predicates using the text from a document

    Args:
        get_text: A function that returns the source text of a node
    """

    def __init__(self, get_text: Callable[[Node], str]):
        self.get_text = get_text
        self._regex_cache: dict[str, re.Pattern | None] = {}

    def _regex(self, pattern: str) -> re.Pattern | None:
        if pattern not in self._regex_cache:
            try:
                self._regex_cache[pattern] = re.compile(lua_to_regex(pattern))
            except re.error:
                self._regex_cache[pattern] = None
        return self._regex_cache[pattern]

    def __call__(self, name: str, args, pattern_index: int, captures) -> bool:
        if not name.startswith(PREFIX):
            # Not one of ours. Don't filter anything out
            return True
        name = name[len(PREFIX) : -1]
        negate = name.startswith("not-")
        if negate:
            name = name[4:]

        if not args or args[0][1] != "capture":
            return True
        nodes = captures.get(args[0][0], [])
        rest = args[1:]

        if name == "eq":
            if not rest:
                return True
            value, kind = rest[0]
            if kind == "capture":
                others = captures.get(value, [])
                if not others:
                    return True
                other = self.get_text(others[0])
                check = lambda text: text == other
            else:
                check = lambda text: text == value

        elif name in ("match", "lua-match"):
            # The nvim queries use lua classes in #match? too, so treat them the same
            if not rest:
                return True
            regex = self._regex(rest[0][0])
            if regex is None:
                return False
            check = lambda text: regex.search(text) is not None

        elif name == "any-of":
            values = {value for value, _kind in rest}
            check = lambda text: text in values

        else:
            return True

        for node in nodes:
            if check(self.get_text(node)) == negate:
                return False
        return True
