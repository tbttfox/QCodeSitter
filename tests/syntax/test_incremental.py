"""
Tests for incremental updates after edits.

Syntax highlighting and code folding only update the parts of the document that
changed, so check that they end up the same as a full update would.
"""

from __future__ import annotations

import random

from Qt import QtCore

from QCodeSitter.behaviors.auto_bracket import AutoBracket
from QCodeSitter.behaviors.code_folding import CodeFolding
from tests.helpers import (
    assert_matches_full_highlight,
    assert_tree_matches_fresh_parse,
    set_cursor_position,
    simulate_keypress,
)

SAMPLE = """import os

MAX_SIZE = 10

def hello(name):
    if name:
        print(f"Hello, {name}!")
    return name

class Greeter:
    def greet(self, name):
        return self.name
"""


def _load(editor, text=SAMPLE):
    editor.setPlainText(text)
    editor.tree_manager.parse_from_scratch()
    editor.remove_behavior(AutoBracket)


class TestIncrementalHighlighting:
    def test_typing(self, editor, qtbot):
        """Test typing that only changes the text a predicate looks at"""
        _load(editor)
        # "MAX_SIZE" -> "MAX_SIZEx" stops being a constant
        set_cursor_position(editor, SAMPLE.index(" = 10"))
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_X, "x")
        assert_matches_full_highlight(editor)

    def test_structure_change_below_edit(self, editor, qtbot):
        """Test an edit that changes the syntax of the rest of the document"""
        _load(editor)
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.insertText('"""\n')
        assert_matches_full_highlight(editor)

        cursor.setPosition(0)
        cursor.setPosition(4, cursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        assert_matches_full_highlight(editor)

    def test_multicursor_newlines(self, editor, qtbot):
        """Test edits at several cursors that add lines"""
        _load(editor)
        set_cursor_position(editor, SAMPLE.index("import"))
        for _ in range(3):
            editor.cursors.add_below()
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return, "\n")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Q, "q")
        assert_matches_full_highlight(editor)

    def test_random_edits(self, editor, qtbot):
        """Test a bunch of random edits"""
        # Non-BMP characters are left out because a random delete can split a
        # surrogate pair, which the editor can't do
        snippets = [
            '"""',
            '"',
            "'",
            "\n",
            "(",
            ")",
            "def f(x):\n    ",
            "MAX",
            "self",
            "# c",
            "é",
        ]
        _load(editor, SAMPLE * 3)
        rng = random.Random(1234)
        for _ in range(300):
            end = editor.document().characterCount() - 1
            cursor = editor.textCursor()
            cursor.setPosition(rng.randint(0, end))
            if rng.random() < 0.6:
                cursor.insertText(rng.choice(snippets))
            else:
                cursor.setPosition(
                    min(end, cursor.position() + rng.randint(1, 40)),
                    cursor.MoveMode.KeepAnchor,
                )
                cursor.removeSelectedText()
            assert_matches_full_highlight(editor)

    def test_delete_lines(self, editor, qtbot):
        """Test deleting several lines with a selection"""
        _load(editor)
        cursor = editor.textCursor()
        cursor.setPosition(SAMPLE.index("def hello"))
        cursor.setPosition(SAMPLE.index("class"), cursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert_matches_full_highlight(editor)


class TestIncrementalFolding:
    def test_folds_update_after_edit(self, editor, qtbot):
        """Test fold regions use the tree from after the edit"""
        _load(editor, "x = 1\n")
        folding = editor.get_behavior(CodeFolding)
        assert folding.regions == []

        set_cursor_position(editor, len("x = 1\n"))
        cursor = editor.textCursor()
        cursor.insertText("def foo():\n    pass\n")
        regions = folding.regions
        assert [(r.start_line, r.end_line) for r in regions] == [(1, 2)]

    def test_fold_depth(self, editor, qtbot):
        _load(editor)
        folding = editor.get_behavior(CodeFolding)
        depths = {(r.node.type, r.start_line): r.depth for r in folding.regions}
        assert depths[("function_definition", 4)] == 0
        assert depths[("if_statement", 5)] == 1
        assert depths[("class_definition", 9)] == 0
        assert depths[("function_definition", 10)] == 1


class TestTrackedCursorDeletes:
    """The incremental tree should match a fresh parse after deletes"""

    def test_delete_char(self, editor, qtbot):
        _load(editor, "ab = 1\nx = (1)\n")
        cursor = editor.textCursor()
        cursor.setPosition(len("ab = 1\nx = "))
        cursor.deleteChar()
        assert editor.toPlainText() == "ab = 1\nx = 1)\n"
        assert_tree_matches_fresh_parse(editor)

    def test_delete_previous_char(self, editor, qtbot):
        _load(editor, "ab = 1\nx = (1)\n")
        cursor = editor.textCursor()
        cursor.setPosition(len("ab = 1\nx = (1)"))
        cursor.deletePreviousChar()
        assert editor.toPlainText() == "ab = 1\nx = (1\n"
        assert_tree_matches_fresh_parse(editor)

    def test_delete_char_with_selection(self, editor, qtbot):
        _load(editor, "ab = 1\nx = (1)\n")
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(len("ab = 1\n"), cursor.MoveMode.KeepAnchor)
        cursor.deleteChar()
        assert editor.toPlainText() == "x = (1)\n"
        assert_tree_matches_fresh_parse(editor)


class TestAutoBracketDeletePair:
    def test_delete_pair_far_into_line(self, editor, qtbot):
        """Test deleting an empty pair after column 3 removes both brackets"""
        editor.setPlainText("print(x, ())  # comment")
        set_cursor_position(editor, len("print(x, ("))
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == "print(x, )  # comment"

    def test_delete_triple_quotes(self, editor, qtbot):
        editor.setPlainText('x = """"""')
        set_cursor_position(editor, len('x = """'))
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == "x = "
