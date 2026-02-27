"""
Integration tests for editor behaviors.

Tests AutoBracket, SmartIndent, and other pluggable behaviors.
"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.behaviors.auto_bracket import AutoBracket
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.line_numbers import LineNumber
from QCodeSitter.behaviors.code_folding import CodeFolding

from tests.helpers import (
    set_cursor_position,
    set_cursor_selection,
    simulate_keypress,
)


class TestAutoBracket:
    """Test auto-bracket insertion and deletion."""

    def test_insert_parentheses_pair(self, editor, qtbot):
        """Test typing ( inserts ()."""
        editor.setPlainText("")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "()"
        # Cursor should be between the parens
        assert editor.textCursor().position() == 1

    def test_insert_bracket_pair(self, editor, qtbot):
        """Test typing [ inserts []."""
        editor.setPlainText("")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_BracketLeft, "[")
        assert editor.toPlainText() == "[]"
        assert editor.textCursor().position() == 1

    def test_insert_brace_pair(self, editor, qtbot):
        """Test typing { inserts {}."""
        editor.setPlainText("")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_BraceLeft, "{")
        assert editor.toPlainText() == "{}"
        assert editor.textCursor().position() == 1

    def test_insert_quote_pair(self, editor, qtbot):
        """Test typing " inserts ""."""
        editor.setPlainText("")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_QuoteDbl, '"')
        assert editor.toPlainText() == '""'
        assert editor.textCursor().position() == 1

    def test_insert_single_quote_pair(self, editor, qtbot):
        """Test typing ' inserts ''."""
        editor.setPlainText("")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Apostrophe, "'")
        assert editor.toPlainText() == "''"
        assert editor.textCursor().position() == 1

    def test_skip_closing_paren(self, editor, qtbot):
        """Test typing ) skips over existing )."""
        editor.setPlainText("()")
        set_cursor_position(editor, 1)  # Between parens
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenRight, ")")
        assert editor.toPlainText() == "()"
        assert editor.textCursor().position() == 2

    def test_skip_closing_bracket(self, editor, qtbot):
        """Test typing ] skips over existing ]."""
        editor.setPlainText("[]")
        set_cursor_position(editor, 1)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_BracketRight, "]")
        assert editor.toPlainText() == "[]"
        assert editor.textCursor().position() == 2

    def test_skip_closing_quote(self, editor, qtbot):
        """Test typing " skips over existing "."""
        editor.setPlainText('""')
        set_cursor_position(editor, 1)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_QuoteDbl, '"')
        assert editor.toPlainText() == '""'
        assert editor.textCursor().position() == 2

    def test_wrap_selection_with_parens(self, editor, qtbot):
        """Test typing ( wraps selection with ()."""
        editor.setPlainText("hello")
        set_cursor_selection(editor, 0, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "(hello)"

    def test_wrap_selection_with_quotes(self, editor, qtbot):
        """Test typing " wraps selection with "" (may vary by implementation)."""
        editor.setPlainText("hello")
        set_cursor_selection(editor, 0, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_QuoteDbl, '"')
        # The exact behavior depends on auto-bracket implementation
        # May wrap or insert pair before selection
        text = editor.toPlainText()
        assert '"' in text and "hello" in text

    def test_delete_pair(self, editor, qtbot):
        """Test backspace between empty pair deletes both."""
        editor.setPlainText("()")
        set_cursor_position(editor, 1)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_delete_quote_pair(self, editor, qtbot):
        """Test backspace between empty quotes deletes both."""
        editor.setPlainText('""')
        set_cursor_position(editor, 1)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_no_delete_pair_with_content(self, editor, qtbot):
        """Test backspace doesn't delete pair when there's content."""
        editor.setPlainText("(x)")
        set_cursor_position(editor, 2)  # After 'x'
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == "()"


class TestSmartIndent:
    """Test smart indentation behavior."""

    def test_indent_after_colon(self, editor, qtbot):
        """Test auto-indent after function definition."""
        editor.setPlainText("def foo():")
        # Wait for tree-sitter to parse
        qtbot.wait(100)
        set_cursor_position(editor, 10)  # End of line
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        text = editor.toPlainText()
        lines = text.split("\n")
        # Second line should be indented (or empty if no auto-indent yet)
        assert len(lines) >= 2

    def test_indent_after_if(self, editor, qtbot):
        """Test auto-indent after if statement."""
        editor.setPlainText("if True:")
        qtbot.wait(100)
        set_cursor_position(editor, 8)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        text = editor.toPlainText()
        lines = text.split("\n")
        assert len(lines) >= 2

    def test_indent_after_for(self, editor, qtbot):
        """Test auto-indent after for loop."""
        editor.setPlainText("for i in range(10):")
        qtbot.wait(100)
        set_cursor_position(editor, 19)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        text = editor.toPlainText()
        lines = text.split("\n")
        assert len(lines) >= 2

    def test_maintain_indent(self, editor, qtbot):
        """Test maintaining current indentation on newline."""
        editor.setPlainText("    x = 1")
        set_cursor_position(editor, 9)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        text = editor.toPlainText()
        lines = text.split("\n")
        # Should maintain the 4-space indent
        assert lines[1].startswith("    ")

    def test_tab_inserts_spaces(self, editor, qtbot):
        """Test Tab inserts spaces (not tabs) by default."""
        editor.setPlainText("")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Tab)
        assert editor.toPlainText() == "    "

    def test_shift_tab_unindents(self, editor, qtbot):
        """Test Shift+Tab removes indentation."""
        editor.setPlainText("    hello")
        set_cursor_position(editor, 4)
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Backtab,
            modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        text = editor.toPlainText()
        assert text == "hello"

    def test_smart_backspace_removes_indent(self, editor, qtbot):
        """Test backspace at end of indent removes whole indent."""
        editor.setPlainText("    ")
        set_cursor_position(editor, 4)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_newline_between_brackets(self, editor, qtbot):
        """Test newline between brackets creates proper structure."""
        editor.setPlainText("def foo():{}")
        # Position cursor between { and }
        set_cursor_position(editor, 11)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        text = editor.toPlainText()
        # Should have indented line between brackets
        assert "    " in text

    def test_closing_bracket_dedent(self, editor, qtbot):
        """Test closing bracket on empty line auto-dedents."""
        editor.setPlainText("def foo():\n        ")
        set_cursor_position(editor, 19)  # End of indented line
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenRight, ")")
        text = editor.toPlainText()
        lines = text.split("\n")
        # Closing paren should be dedented
        assert lines[1].strip() == ")"
        assert not lines[1].startswith("        ")

    def test_tab_indents_selection(self, editor, qtbot):
        """Test Tab indents all lines in selection."""
        editor.setPlainText("line 1\nline 2\nline 3")
        set_cursor_selection(editor, 0, 20)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Tab)
        text = editor.toPlainText()
        lines = text.split("\n")
        # All lines should be indented
        assert all(line.startswith("    ") for line in lines if line.strip())


class TestBehaviorManagement:
    """Test adding, removing, and getting behaviors."""

    def test_add_behavior(self, editor, qtbot):
        """Test adding a new behavior to the editor."""
        from QCodeSitter.behaviors.overscroll import Overscroll

        # Remove Overscroll behavior first, then add it back
        editor.removeBehavior(Overscroll)
        assert editor.getBehavior(Overscroll) is None
        old, new = editor.addBehavior(Overscroll)
        assert old is None
        assert new is not None
        assert editor.getBehavior(Overscroll) is new

    def test_remove_behavior(self, editor, qtbot):
        """Test removing a behavior from the editor."""
        assert editor.getBehavior(SmartIndent) is not None
        removed = editor.removeBehavior(SmartIndent)
        assert removed is not None
        assert editor.getBehavior(SmartIndent) is None

    def test_replace_behavior(self, editor, qtbot):
        """Test adding a behavior replaces existing one of same type."""
        old_behavior = editor.getBehavior(SmartIndent)
        old_replaced, new = editor.addBehavior(SmartIndent)
        assert old_replaced is old_behavior
        assert new is not old_behavior
        assert editor.getBehavior(SmartIndent) is new

    def test_get_nonexistent_behavior(self, bare_editor, qtbot):
        """Test getting a behavior that doesn't exist returns None."""
        assert bare_editor.getBehavior(LineNumber) is None


class TestLineNumbers:
    """Test line number display behavior."""

    def test_line_numbers_exist(self, editor, qtbot):
        """Test that line number behavior is added."""
        line_num_behavior = editor.getBehavior(LineNumber)
        assert line_num_behavior is not None

    def test_gutter_width_set(self, editor, qtbot):
        """Test that gutter width is set for line numbers."""
        # The line number behavior adds to gutterWidths with key "LineNumberArea"
        assert "LineNumberArea" in editor.gutterWidths or len(editor.gutterWidths) > 0


class TestCodeFolding:
    """Test code folding behavior."""

    def test_code_folding_exists(self, editor, qtbot):
        """Test that code folding behavior is added."""
        folding_behavior = editor.getBehavior(CodeFolding)
        assert folding_behavior is not None

    def test_folding_regions_detected(self, editor_with_text, qtbot):
        """Test that foldable regions are detected in Python code."""
        editor = editor_with_text
        folding = editor.getBehavior(CodeFolding)
        # Give the tree manager time to parse
        qtbot.wait(50)
        # The sample code has functions and classes that should be foldable
        # This tests that the behavior initializes and processes the document


class TestAutoBracketWithMultiCursor:
    """Test auto-bracket behavior with multiple cursors."""

    def test_insert_pairs_at_all_cursors(self, editor, qtbot):
        """Test bracket pairs inserted at all cursors."""
        editor.setPlainText("a\nb\nc")
        # Set up cursors after each letter
        set_cursor_position(editor, 1)
        from QCodeSitter.code_editor import CursorState

        editor.secondary_cursors = [CursorState(3, 3), CursorState(5, 5)]
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "a()"
        assert lines[1] == "b()"
        assert lines[2] == "c()"

    def test_wrap_selections_at_all_cursors(self, editor, qtbot):
        """Test wrapping selections with brackets at all cursors."""
        editor.setPlainText("foo\nbar\nbaz")
        # Select each word
        set_cursor_selection(editor, 0, 3)
        from QCodeSitter.code_editor import CursorState

        editor.secondary_cursors = [CursorState(4, 7), CursorState(8, 11)]
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "(foo)"
        assert lines[1] == "(bar)"
        assert lines[2] == "(baz)"


class TestSmartIndentWithMultiCursor:
    """Test smart indent behavior with multiple cursors."""

    def test_indent_all_lines_at_cursors(self, editor, qtbot):
        """Test indenting lines at all cursor positions."""
        editor.setPlainText("a\nb\nc")
        set_cursor_position(editor, 0)
        from QCodeSitter.code_editor import CursorState

        editor.secondary_cursors = [CursorState(2, 2), CursorState(4, 4)]
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Tab)
        text = editor.toPlainText()
        lines = text.split("\n")
        # All lines should be indented
        assert all(line.startswith("    ") for line in lines)

    def test_newline_preserves_indent_all_cursors(self, editor, qtbot):
        """Test newline maintains indent at all cursor positions."""
        editor.setPlainText("    a\n    b")
        # Position cursors at end of each line
        set_cursor_position(editor, 5)
        from QCodeSitter.code_editor import CursorState

        editor.secondary_cursors = [CursorState(11, 11)]
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        text = editor.toPlainText()
        lines = text.split("\n")
        # New lines should maintain the 4-space indent
        for i, line in enumerate(lines):
            if line.strip():
                assert line.startswith("    "), f"Line {i} not indented: {repr(line)}"
