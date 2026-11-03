"""Tests for compiling and running tree-sitter queries, and their text predicates"""

from __future__ import annotations

import re
import warnings

import pytest
from tree_sitter import Query

from QCodeSitter.queries import compile_query, query_byte_range
from QCodeSitter.queries.predicates import (
    PREFIX,
    QueryPredicates,
    lua_to_regex,
    prepare_query_source,
)
from QCodeSitter.tracked_document import TrackedDocument
from QCodeSitter.tree_manager import TreeManager


class TestPredicates:
    def test_prepare_query_source(self):
        source = '((identifier) @x (#eq? @x "self") (#not-match? @x "^_"))'
        assert prepare_query_source(source) == (
            f'((identifier) @x (#{PREFIX}eq? @x "self") (#{PREFIX}not-match? @x "^_"))'
        )

    @pytest.mark.parametrize(
        "pattern, text, matches",
        [
            ("^%u", "Foo", True),
            ("^%u", "foo", False),
            ("^[%u_]+$", "MAX_SIZE", True),
            ("%d+", "a1", True),
            ("^%U", "foo", True),
            ("a%.b", "a.b", True),
            ("a%.b", "axb", False),
        ],
    )
    def test_lua_to_regex(self, pattern, text, matches):
        assert (re.search(lua_to_regex(pattern), text) is not None) is matches

    def test_lua_complement_in_set_is_an_error(self):
        with pytest.raises(re.error):
            lua_to_regex("[%U]")

    @staticmethod
    def call(predicates, name, args, captures):
        return predicates(f"{PREFIX}{name}?", args, 0, captures)

    def test_predicates(self):
        texts = {"a": "self", "b": "self", "c": "other"}
        predicates = QueryPredicates(lambda node: texts[node])
        caps = {"x": ["a"], "y": ["b"], "z": ["c"]}
        assert self.call(predicates, "eq", [("x", "capture"), ("self", "string")], caps)
        assert self.call(predicates, "eq", [("x", "capture"), ("y", "capture")], caps)
        assert not self.call(
            predicates, "eq", [("x", "capture"), ("z", "capture")], caps
        )
        assert self.call(
            predicates, "not-eq", [("z", "capture"), ("self", "string")], caps
        )
        assert self.call(
            predicates,
            "any-of",
            [("z", "capture"), ("a", "string"), ("other", "string")],
            caps,
        )
        assert self.call(
            predicates, "match", [("x", "capture"), ("^s", "string")], caps
        )
        assert not self.call(
            predicates, "not-match", [("x", "capture"), ("^s", "string")], caps
        )

    def test_other_predicates_pass(self):
        predicates = QueryPredicates(lambda node: "")
        assert predicates("set!", [], 0, {})
        assert predicates(f"{PREFIX}eq?", [("x", "capture")], 0, {"x": ["a"]})

    def test_invalid_pattern_warns_and_filters(self):
        predicates = QueryPredicates(lambda node: "text")
        with pytest.warns(UserWarning, match="Invalid #match"):
            assert not self.call(
                predicates,
                "match",
                [("x", "capture"), ("[%U]", "string")],
                {"x": ["a"]},
            )


class TestTreeManagerQueries:
    def test_query_byte_range(self, editor):
        editor.setPlainText("x = 1\ny = 2\n")
        manager: TreeManager = editor.tree_manager
        query = Query(manager.language, "(identifier) @name")
        root = manager.root_node
        everything = query_byte_range(query, root, 0, root.end_byte)["name"]
        assert [n.start_point.row for n in everything] == [0, 1]
        # The second line starts at char 6, which is byte 12
        second = query_byte_range(query, root, 12, root.end_byte)["name"]
        assert [n.start_point.row for n in second] == [1]

    def test_predicate_errors_propagate(self, editor):
        editor.setPlainText("x = 1")
        query = Query(
            editor.tree_manager.language, '((identifier) @name (#qcs-eq? @name "x"))'
        )
        root = editor.tree_manager.root_node

        def failing_get_text(_node):
            raise ValueError("bad text")

        with pytest.raises(ValueError, match="bad text"):
            query_byte_range(query, root, 0, root.end_byte, failing_get_text)

    def test_reversed_byte_range_is_empty(self, editor):
        editor.setPlainText("x = 1")
        query = Query(editor.tree_manager.language, "(identifier) @name")
        root = editor.tree_manager.root_node
        with pytest.warns(UserWarning, match="reversed byte range 5..2"):
            assert query_byte_range(query, root, 5, 2) == {}

    def test_invalid_query_warns_once(self, python_language):
        with pytest.warns(UserWarning, match="Invalid tree-sitter query for python"):
            assert compile_query(python_language, "(not_a_node) @x") is None
        # The failure is cached, so it doesn't warn again
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert compile_query(python_language, "(not_a_node) @x") is None

    def test_tree_manager_only_needs_a_document(self, python_language):
        document = TrackedDocument()
        document.setPlainText("x = 1\n")
        manager = TreeManager(document)
        manager.set_language(python_language)
        assert manager.node_at_char(0).type == "identifier"
