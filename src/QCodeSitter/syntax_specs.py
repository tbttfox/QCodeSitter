"""The "syntax" option: text formats keyed by tree-sitter capture name, and how
dotted capture names fall back to their parents
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict, TypeVar


class SyntaxSpec(TypedDict, total=False):
    color: str
    italic: bool
    bold: bool


# Tree-sitter capture name -> format
SyntaxSpecs = dict[str, SyntaxSpec]

T = TypeVar("T")


def resolve_capture(name: str, specs: Mapping[str, T]) -> T | None:
    """Look up a treesitter capture name, falling back to its parent groups

    For example "function.method.call" will check "function.method.call", then
    "function.method", then "function". This mirrors how nvim resolves highlight groups

    Args:
        name: The dotted treesitter capture name
        specs: A dictionary keyed by capture names

    Returns:
        The value of the most specific matching key, or None if nothing matches
    """
    parts = name.split(".")
    while parts:
        val = specs.get(".".join(parts))
        if val is not None:
            return val
        parts.pop()
    return None


def overlay_syntax(base: SyntaxSpecs, overrides: SyntaxSpecs) -> SyntaxSpecs:
    """Overlay syntax specs onto a base set of syntax specs

    Overrides are resolved hierarchically, so an override for "keyword" will replace
    the base "keyword.return" unless there is also an override for "keyword.return".

    Args:
        base: A syntax spec dictionary as returned by read_theme
        overrides: A partial syntax spec dictionary

    Returns:
        A new syntax spec dictionary
    """
    names = set(base) | set(overrides)
    out: SyntaxSpecs = {}
    for name in names:
        spec = resolve_capture(name, overrides)
        if spec is None:
            spec = base[name]
        out[name] = spec.copy()
    return out
