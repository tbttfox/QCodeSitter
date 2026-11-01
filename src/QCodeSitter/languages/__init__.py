"""Per-language knowledge, looked up from the editor's tree-sitter language

Add support for a language by registering a LanguageSpec for its grammar name.
The query functions compile the queries of the language's current spec, so
registering a new spec takes effect the next time a behavior asks for a query.
Syntax highlighting asks when the language or the "syntax" option changes.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from tree_sitter import Query

from ..highlighting.predicates import prepare_query_source
from .base import IndentRules, LanguageSpec
from .python import PYTHON

if TYPE_CHECKING:
    from tree_sitter import Language


class LanguageRegistry:
    """The LanguageSpecs the behaviors use, by tree-sitter grammar name"""

    def __init__(self, specs: tuple[LanguageSpec, ...] = ()) -> None:
        self._specs = {spec.name: spec for spec in specs}

    def register(self, spec: LanguageSpec) -> None:
        """Add a language, or replace the spec of one with the same name"""
        self._specs[spec.name] = spec

    def spec_for(self, language: Language | None) -> LanguageSpec:
        """Get the spec for a language, or a plain spec if it isn't registered"""
        name = language.name if language is not None else None
        if not name:
            return LanguageSpec("")
        spec = self._specs.get(name)
        return spec if spec is not None else LanguageSpec(name)


LANGUAGES = LanguageRegistry(
    (
        PYTHON,
        LanguageSpec("bash", comment_prefix="# "),
        LanguageSpec("c", comment_prefix="// "),
        LanguageSpec("cpp", comment_prefix="// "),
        LanguageSpec("lua", comment_prefix="-- "),
    )
)
register_language = LANGUAGES.register
language_spec = LANGUAGES.spec_for


@functools.cache
def _compile(language: Language, source: str) -> Query:
    """Compile a query once, and share it between every editor and behavior"""
    return Query(language, source)


def highlight_query(language: Language) -> Query | None:
    """The language's highlight query, ready for QueryPredicates to evaluate"""
    source = language_spec(language).highlight_query
    return _compile(language, prepare_query_source(source)) if source else None


def identifier_query(language: Language) -> Query | None:
    """The query that captures the names defined in a document"""
    source = language_spec(language).identifier_query
    return _compile(language, source) if source else None


def foldable_query(language: Language) -> Query | None:
    """A query that captures every foldable node in the language as @fold"""
    types = [
        t
        for t in sorted(language_spec(language).foldable_types)
        if language.id_for_node_kind(t, True)
    ]
    if not types:
        return None
    return _compile(language, "[{}] @fold".format(" ".join(f"({t})" for t in types)))


__all__ = [
    "LANGUAGES",
    "IndentRules",
    "LanguageRegistry",
    "LanguageSpec",
    "foldable_query",
    "highlight_query",
    "identifier_query",
    "language_spec",
    "register_language",
]
