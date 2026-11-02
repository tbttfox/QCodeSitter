"""Per-language knowledge, looked up from the editor's tree-sitter language

Add support for a language by registering a LanguageSpec for its grammar name.
The query functions compile the queries of the language's current spec, so
registering a new spec takes effect the next time a behavior asks for a query.
Syntax highlighting asks when the language or the "syntax" option changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..queries import compile_query
from .base import IndentRules, LanguageSpec
from .python import PYTHON

if TYPE_CHECKING:
    from tree_sitter import Language, Query

# The languages that are registered when QCodeSitter is imported
BUILTIN_LANGUAGES = (
    PYTHON,
    LanguageSpec("bash", comment_prefix="# "),
    LanguageSpec("c", comment_prefix="// "),
    LanguageSpec("cpp", comment_prefix="// "),
    LanguageSpec("lua", comment_prefix="-- "),
)


class LanguageRegistry:
    """The LanguageSpecs the behaviors use, by tree-sitter grammar name

    There is one registry for the process, LANGUAGES, so registering a
    language adds it to every editor
    """

    def __init__(self, specs: tuple[LanguageSpec, ...] = ()) -> None:
        self._initial = specs
        self._specs = {spec.name: spec for spec in specs}

    def reset(self) -> None:
        """Go back to the specs the registry was made with"""
        self._specs = {spec.name: spec for spec in self._initial}

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


LANGUAGES = LanguageRegistry(BUILTIN_LANGUAGES)
register_language = LANGUAGES.register
language_spec = LANGUAGES.spec_for


def highlight_query(language: Language) -> Query | None:
    """The language's highlight query"""
    source = language_spec(language).highlight_query
    return compile_query(language, source) if source else None


def identifier_query(language: Language) -> Query | None:
    """The query that captures the names defined in a document"""
    source = language_spec(language).identifier_query
    return compile_query(language, source) if source else None


def foldable_query(language: Language) -> Query | None:
    """A query that captures every foldable node in the language as @fold"""
    types = [
        t
        for t in sorted(language_spec(language).foldable_types)
        if language.id_for_node_kind(t, True)
    ]
    if not types:
        return None
    patterns = " ".join(f"({t})" for t in types)
    return compile_query(language, f"[{patterns}] @fold")


__all__ = [
    "BUILTIN_LANGUAGES",
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
