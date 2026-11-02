"""
Integration tests for syntax analysis and tree-sitter integration.

Tests TreeManager, the python IndentRules, TrackedDocument, and syntax highlighting.
Parsing and highlighting happen synchronously, so no test needs to wait.
"""

from __future__ import annotations

import re
import warnings

import pytest
from Qt import QtCore, QtGui
from tree_sitter import Point, Query

from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.cursors.tracked import TrackedCursor
from QCodeSitter.languages import (
    language_spec,
)
from QCodeSitter.languages.python import PythonIndentRules
from QCodeSitter.queries import compile_query, query_byte_range
from QCodeSitter.queries.predicates import (
    PREFIX,
    QueryPredicates,
    lua_to_regex,
    prepare_query_source,
)
from QCodeSitter.tracked_document import ENC, TrackedDocument
from QCodeSitter.tree_manager import TreeManager
from tests.helpers import (
    assert_matches_full_highlight,
    assert_tree_matches_fresh_parse,
    fresh_tree_str,
    set_cursor_position,
    simulate_keypress,
)


class TestTrackedDocument:
    def test_document_creation(self, editor):
        assert isinstance(editor.document(), TrackedDocument)

    def test_byte_contents_change_signal(self, editor):
        """Typing emits the edit in UTF-16LE bytes"""
        editor.setPlainText("é𝒳")
        set_cursor_position(editor, 3)
        received = []
        editor.document().byteContentsChange.connect(
            lambda *args: received.append(args)
        )
        simulate_keypress(editor, QtCore.Qt.Key.Key_A, "a")
        # 3 code units are 6 bytes, and "a" is 2 more
        assert received == [(6, 6, 8, Point(0, 6), Point(0, 6), Point(0, 8))]

    def test_multiline_change_points(self, editor):
        editor.setPlainText("ab\ncd")
        received = []
        editor.document().byteContentsChange.connect(
            lambda *args: received.append(args)
        )
        editor.document().report_edit(1, "b\u2029c", "")
        assert received == [(2, 8, 2, Point(0, 2), Point(1, 2), Point(0, 2))]

    def test_byte_char_conversion(self):
        assert TrackedDocument.char_to_byte(5) == 10
        assert TrackedDocument.byte_to_char(10) == 5

    def test_row_col_to_char(self, editor):
        editor.setPlainText("abc\ndef")
        assert editor.document().row_col_to_char(1, 2) == 6


class TestTreeManager:
    def test_tree_root_node(self, editor_with_text):
        assert editor_with_text.tree_manager.root_node.type == "module"

    def test_incremental_update(self, editor):
        """The incremental tree matches a fresh parse after typing"""
        editor.setPlainText("x = 1")
        set_cursor_position(editor, 5)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Plus, "+")
        simulate_keypress(editor, QtCore.Qt.Key.Key_2, "2")

        assert editor.toPlainText() == "x = 1+2"
        tree = editor.tree_manager.tree
        assert "binary_operator" in str(tree.root_node)
        assert str(tree.root_node) == fresh_tree_str(editor)

    def test_node_at_byte_and_char(self, editor_with_text):
        manager = editor_with_text.tree_manager
        assert manager.node_at_byte(0).type == "def"
        # "hello" starts at char 4, which is byte 8
        assert manager.node_at_char(4).type == "identifier"
        assert manager.node_at_byte(8) == manager.node_at_char(4)

    def test_pause_defers_reparse(self, editor):
        """Edits while paused are parsed once on unpause"""
        editor.setPlainText("x = 1")
        reparses = []
        editor.tree_manager.reparsed.connect(lambda: reparses.append(1))

        editor.tree_manager.pause()
        assert editor.tree_manager.is_paused
        set_cursor_position(editor, 5)
        cursor = editor.textCursor()
        cursor.insertText("2")
        cursor.insertText("3")
        assert reparses == []

        editor.tree_manager.unpause()
        assert not editor.tree_manager.is_paused
        assert reparses == [1]
        assert str(editor.tree_manager.root_node) == fresh_tree_str(editor)

    def test_set_language_none(self, editor):
        changes = []
        editor.tree_manager.languageChanged.connect(lambda: changes.append(1))
        editor.tree_manager.set_language(None)
        assert changes == [1]
        assert editor.tree_manager.tree is None
        assert editor.tree_manager.language is None

    def test_set_language_reparses(self, editor, python_language):
        editor.tree_manager.set_language(None)
        editor.setPlainText("x = 1")
        editor.tree_manager.set_language(python_language)
        assert str(editor.tree_manager.root_node) == fresh_tree_str(editor)


class TestPythonIndentRules:
    @staticmethod
    def rules(editor, text: str) -> PythonIndentRules:
        editor.setPlainText(text)
        return PythonIndentRules(editor.tree_manager, editor.document())

    def test_language_spec(self, editor):
        spec = language_spec(editor.tree_manager.language)
        assert spec.name == "python"
        assert spec.indent_rules is PythonIndentRules

    @pytest.mark.parametrize(
        "text, col, expected",
        [
            ("def foo():", 9, True),
            ("if True:", 7, True),
            ("if True:  # comment", 18, True),
            ("x = [", 4, True),
            ("x = 1", 4, False),
            ("x = [1]", 6, False),
        ],
    )
    def test_should_indent_after(self, editor, text, col, expected):
        assert self.rules(editor, text).should_indent_after(0, col) is expected

    @pytest.mark.parametrize(
        "text, row, col, expected",
        [
            ("def foo():\n    return 1", 1, 11, True),
            ("def foo():\n    pass", 1, 7, True),
            ("for x in y:\n    break", 1, 8, True),
            ("def foo():\n    x = 1", 1, 8, False),
            # Enter before a closing bracket on its own line
            ("x = [\n    1,\n    ]", 2, 1, True),
            # Enter after the closing bracket keeps the indent
            ("x = [\n    1,\n    ]", 2, 4, False),
        ],
    )
    def test_should_dedent_after(self, editor, text, row, col, expected):
        line = text.split("\n")[row]
        assert self.rules(editor, text).should_dedent_after(row, col, line) is expected


class TestSyntaxHighlighting:
    @staticmethod
    def _token_color(editor, line, token):
        block = editor.document().findBlockByNumber(line)
        text = block.text()
        # Qt format ranges are in UTF-16 code units
        start = len(text[: text.index(token)].encode("utf-16-le")) // 2
        length = len(token.encode("utf-16-le")) // 2
        for rng in block.layout().formats():
            if rng.start == start and rng.length == length:
                return rng.format.foreground().color().name()
        return None

    @staticmethod
    def _capture_color(editor, name):
        hl = editor.get_behavior(SyntaxHighlighting).highlighter
        return hl.formats[name].foreground().color().name()

    def test_highlighting_applied(self, editor_with_text):
        assert self._token_color(editor_with_text, 0, "def") == self._capture_color(
            editor_with_text, "keyword.function"
        )

    def test_highlighting_updates_on_typing(self, editor):
        """Typing a keyword highlights it as one"""
        editor.setPlainText("x = 1\n")
        set_cursor_position(editor, 6)
        for char in "return":
            simulate_keypress(editor, QtCore.Qt.Key.Key_unknown, char)
        assert self._token_color(editor, 1, "return") == self._capture_color(
            editor, "keyword.return"
        )

    @pytest.mark.parametrize(
        "text, token, capture",
        [
            ("x = self.y", "self", "variable.builtin"),  # #eq?
            ("MAX_SIZE = 1", "MAX_SIZE", "constant"),  # #match?
            ("x = __name__", "__name__", "constant.builtin"),  # #match?
            ("print(x)", "print", "function.builtin"),  # #any-of?
            ("x = foo.bar", "bar", "variable.member"),  # #match? with lua classes
            ("x = Foo(1)", "Foo", "constructor"),  # #match? with lua classes
            ("é𝒳 = self", "self", "variable.builtin"),  # surrogate pairs before
        ],
    )
    def test_text_predicates(self, editor, text, token, capture):
        """Test captures that depend on text predicates get their format.

        The tree is parsed from a callback so tree-sitter can't evaluate the
        text predicates itself.
        """
        editor.setPlainText(text)
        assert self._token_color(editor, 0, token) == self._capture_color(
            editor, capture
        )

    def test_text_predicate_negative(self, editor):
        editor.setPlainText("x = selfish")
        assert self._token_color(editor, 0, "selfish") == self._capture_color(
            editor, "variable"
        )

    def test_highlighting_after_undo(self, editor, qtbot):
        """Undo rebuilds the tree and the highlighting"""
        editor.setPlainText("x = 1\n")
        set_cursor_position(editor, 6)
        for char in "return":
            simulate_keypress(editor, QtCore.Qt.Key.Key_unknown, char)
        editor.undo()
        qtbot.waitUntil(
            lambda: str(editor.tree_manager.root_node) == fresh_tree_str(editor)
        )
        assert editor.toPlainText() == "x = 1\n"

    def test_undo_and_redo_rehighlight_straight_away(self, editor):
        editor.setPlainText("def f():\n    return 1\n")
        set_cursor_position(editor, 9)
        editor.insert_text('x = """\n')
        for action in (editor.undo, editor.redo):
            action()
            assert_tree_matches_fresh_parse(editor)
            assert_matches_full_highlight(editor)

    def test_follows_language_changes(self, editor, python_language):
        """The query comes from the language, so changing it changes the highlighting"""
        editor.setPlainText("def foo(): pass")
        assert self._token_color(editor, 0, "def") is not None
        editor.tree_manager.set_language(None)
        assert editor.get_behavior(SyntaxHighlighting).highlighter is None
        assert not editor.document().firstBlock().layout().formats()
        editor.tree_manager.set_language(python_language)
        assert self._token_color(editor, 0, "def") is not None

    def test_syntax_set_before_language(self, bare_editor, python_language):
        """Syntax formats given before there's a language apply once there is one"""
        bare_editor.tree_manager.set_language(None)
        highlighting = bare_editor.add_behavior(SyntaxHighlighting)
        bare_editor.options["syntax"] = {"keyword": {"color": "#FF0000"}}
        assert highlighting.highlighter is None
        bare_editor.setPlainText("def foo(): pass")
        bare_editor.tree_manager.set_language(python_language)
        assert self._token_color(bare_editor, 0, "def") == "#ff0000"


class TestSyntaxIntegration:
    def test_smart_indent_uses_syntax(self, editor):
        """Enter after a block opener indents the new line"""
        editor.setPlainText("def hello():")
        set_cursor_position(editor, 12)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "def hello():\n    "

    def test_syntax_error_handling(self, editor):
        """Incomplete code still parses, with error nodes"""
        editor.setPlainText("def foo(")
        assert editor.tree_manager.root_node.has_error
        set_cursor_position(editor, 8)
        simulate_keypress(editor, QtCore.Qt.Key.Key_ParenRight, ")")
        assert editor.toPlainText() == "def foo()"
        assert str(editor.tree_manager.root_node) == fresh_tree_str(editor)


class TestUnicodeHandling:
    @pytest.mark.parametrize("text", ['x = "Hello 世界"', 'x = "Hello 🎉"'])
    def test_unicode_in_string(self, editor, text):
        editor.setPlainText(text)
        string = editor.tree_manager.root_node.child(0).child(0).child(2)
        assert string.type == "string"
        # The string node ends at the end of the document, in UTF-16 bytes
        assert string.end_byte == len(text.encode(ENC))

    def test_editing_after_unicode(self, editor):
        editor.setPlainText("日本語🎉")
        set_cursor_position(editor, 5)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Exclam, "!")
        assert editor.toPlainText() == "日本語🎉!"
        assert str(editor.tree_manager.root_node) == fresh_tree_str(editor)


class TestDocumentReload:
    def test_replace_all_text(self, editor):
        editor.setPlainText("def foo(): pass")
        editor.setPlainText("x = 1")
        assert str(editor.tree_manager.root_node) == fresh_tree_str(editor)

    def test_clear(self, editor):
        editor.setPlainText("def foo(): pass")
        editor.setPlainText("")
        assert editor.tree_manager.root_node.child_count == 0


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


class TestTrackedCursor:
    """Every TrackedCursor edit reports the change in UTF-16LE bytes"""

    @pytest.fixture
    def edits(self, bare_editor):
        bare_editor.setPlainText("ab\ncd")
        received = []
        bare_editor.document().byteContentsChange.connect(
            lambda *args: received.append(args)
        )
        return received

    def test_insert_text(self, bare_editor, edits):
        cursor = bare_editor.textCursor()
        assert isinstance(cursor, TrackedCursor)
        cursor.setPosition(1)
        cursor.insertText("X\nY")
        assert edits == [(2, 2, 8, Point(0, 2), Point(0, 2), Point(1, 2))]

    def test_replace_selection(self, bare_editor, edits):
        cursor = bare_editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(4, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("Z")
        assert bare_editor.toPlainText() == "aZd"
        assert edits == [(2, 8, 4, Point(0, 2), Point(1, 2), Point(0, 4))]

    def test_insert_block_over_selection(self, bare_editor, edits):
        cursor = bare_editor.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(4, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.insertBlock()
        assert bare_editor.toPlainText() == "a\nd"
        assert edits == [(2, 8, 4, Point(0, 2), Point(1, 2), Point(1, 0))]
        assert_tree_matches_fresh_parse(bare_editor)

    def test_insert_block(self, bare_editor, edits):
        cursor = bare_editor.textCursor()
        cursor.setPosition(2)
        cursor.insertBlock()
        assert bare_editor.toPlainText() == "ab\n\ncd"
        assert edits == [(4, 4, 6, Point(0, 4), Point(0, 4), Point(1, 0))]

    def test_deletes(self, bare_editor, edits):
        cursor = bare_editor.textCursor()
        cursor.setPosition(1)
        cursor.deleteChar()
        cursor.deletePreviousChar()
        assert bare_editor.toPlainText() == "\ncd"
        assert edits == [
            (2, 4, 2, Point(0, 2), Point(0, 4), Point(0, 2)),
            (0, 2, 0, Point(0, 0), Point(0, 2), Point(0, 0)),
        ]


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

    def test_query_byte_range_failure_is_empty(self, editor):
        editor.setPlainText("x = 1")
        query = Query(
            editor.tree_manager.language, '((identifier) @name (#qcs-eq? @name "x"))'
        )
        root = editor.tree_manager.root_node

        def failing_predicate(*_args):
            raise ValueError("bad predicate")

        with pytest.warns(UserWarning, match="bad predicate"):
            captures = query_byte_range(
                query, root, 0, root.end_byte, failing_predicate
            )
        assert captures == {}

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
