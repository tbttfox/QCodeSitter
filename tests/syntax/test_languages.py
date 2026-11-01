"""Tests for the per-language specs and their registry"""

from __future__ import annotations

import dataclasses

import pytest
from tree_sitter import Language

from QCodeSitter.behaviors.code_folding import CodeFolding
from QCodeSitter.behaviors.comment_toggle import CommentToggle
from QCodeSitter.behaviors.tab_completion.providers import IdentifierProvider
from QCodeSitter.languages import (
    LanguageRegistry,
    LanguageSpec,
    foldable_query,
    highlight_query,
    identifier_query,
    language_spec,
    register_language,
)
from QCodeSitter.languages.base import IndentRules
from QCodeSitter.languages.python import PYTHON


@pytest.fixture
def python_spec():
    """Restore the python spec after a test registers another one"""
    yield PYTHON
    register_language(PYTHON)


class TestLanguages:
    def test_unregistered_language(self):
        assert language_spec(None) == LanguageSpec("")

    def test_comment_prefix_follows_language(self, editor, python_spec):
        register_language(dataclasses.replace(python_spec, comment_prefix="// "))
        assert editor.get_behavior(CommentToggle).comment_prefix == "// "
        register_language(python_spec)
        assert editor.get_behavior(CommentToggle).comment_prefix == "# "

    def test_foldable_types(self, python_language: Language):
        spec = language_spec(python_language)
        assert "function_definition" in spec.foldable_types
        assert "list" in spec.foldable_types


class TestLanguageQueries:
    def test_queries_are_shared(self, python_language):
        """Every editor and behavior uses the same compiled query"""
        assert highlight_query(python_language) is highlight_query(python_language)
        assert identifier_query(python_language) is identifier_query(python_language)
        assert foldable_query(python_language) is foldable_query(python_language)

    def test_language_without_queries(self, python_language, python_spec):
        register_language(LanguageSpec("python"))
        assert highlight_query(python_language) is None
        assert identifier_query(python_language) is None
        assert foldable_query(python_language) is None

    def test_registering_a_spec_changes_the_queries(self, editor, python_spec):
        """Behaviors ask for the queries each time, so a new spec takes effect"""
        editor.setPlainText("def foo():\n    pass\nx = [\n    1,\n]\n")
        register_language(
            dataclasses.replace(
                python_spec,
                identifier_query="(assignment left: (identifier) @variable)",
                fold_hide_last_line=frozenset(),
            )
        )
        names = {c.text for c in IdentifierProvider(editor).provide()}
        assert names == {"x"}
        editor.tree_manager.full_update()
        folding = editor.get_behavior(CodeFolding)
        assert [r.node.type for r in folding.regions] == ["list"]


class TestLanguageBase:
    def test_base_rules_never_change_the_indent(self, editor):
        editor.setPlainText("def foo():")
        rules = IndentRules(editor.tree_manager, editor.document())
        assert not rules.should_indent_after(0, 9)
        assert not rules.should_dedent_after(0, 9, "def foo():")
        assert rules.node_at(0, 0).type == "def"

    def test_registry(self, python_language):
        registry = LanguageRegistry()
        assert registry.spec_for(python_language) == LanguageSpec("python")
        registry.register(LanguageSpec("python", comment_prefix="// "))
        assert registry.spec_for(python_language).comment_prefix == "// "
        assert registry.spec_for(None).name == ""
