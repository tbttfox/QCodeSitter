"""
Integration tests for editor behaviors.

Tests AutoBracket, SmartIndent, and other pluggable behaviors.
"""

from __future__ import annotations

import pytest
from Qt import QtCore

from QCodeSitter.behaviors.highlight_matching_selection import (
    HighlightMatchingSelection,
)
from QCodeSitter.behaviors.line_numbers import LineNumber
from QCodeSitter.behaviors.overscroll import Overscroll
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.cursors.state import CursorState
from tests.helpers import (
    get_cursor_positions,
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
        """Test typing " wraps selection with ""."""
        editor.setPlainText("x = hello")
        set_cursor_selection(editor, 4, 9)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_QuoteDbl, '"')
        assert editor.toPlainText() == 'x = "hello"'
        cursor = editor.textCursor()
        assert (cursor.selectionStart(), cursor.selectionEnd()) == (5, 10)

    def test_pairs_option(self, editor, qtbot):
        """Test the auto_bracket_pairs option changes which pairs are inserted."""
        editor.options["auto_bracket_pairs"] = ["()"]
        editor.setPlainText("")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_BracketLeft, "[")
        assert editor.toPlainText() == "["

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

    @pytest.mark.parametrize(
        "line", ["def foo():", "if True:", "for i in range(10):", "x = ["]
    )
    def test_indent_after_block_opener(self, editor, qtbot, line):
        """Enter after a line that opens a block indents the new line"""
        editor.setPlainText(line)
        set_cursor_position(editor, len(line))
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == line + "\n    "

    def test_dedent_after_return(self, editor, qtbot):
        editor.setPlainText("def foo():\n    return 1")
        set_cursor_position(editor, len(editor.toPlainText()))
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "def foo():\n    return 1\n"

    def test_maintain_indent(self, editor, qtbot):
        """Test maintaining current indentation on newline."""
        editor.setPlainText("    x = 1")
        set_cursor_position(editor, 9)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "    x = 1\n    "

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

    def test_shift_tab_unindents_tabs_over_blank_line(self, editor, qtbot):
        """Test unindenting tab indented lines when the selection has a blank line."""
        editor.options["indent_using_tabs"] = True
        editor.setPlainText("\ta\n\n\tb")
        set_cursor_selection(editor, 0, 6)
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Backtab,
            modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        assert editor.toPlainText() == "a\n\nb"

    def test_smart_backspace_removes_indent(self, editor, qtbot):
        """Test backspace at end of indent removes whole indent."""
        editor.setPlainText("    ")
        set_cursor_position(editor, 4)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_newline_between_brackets(self, editor, qtbot):
        """Enter between brackets puts the closing bracket below an indented line"""
        editor.setPlainText("    x = []")
        set_cursor_position(editor, 9)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "    x = [\n        \n    ]"
        # The cursor is on the indented line
        assert editor.textCursor().position() == len("    x = [\n        ")

    def test_closing_bracket_dedent(self, editor, qtbot):
        """A closing bracket typed on a blank line removes one indent"""
        editor.setPlainText("def foo():\n        ")
        set_cursor_position(editor, 19)  # End of indented line
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenRight, ")")
        assert editor.toPlainText() == "def foo():\n    )"

    def test_tab_indents_selection(self, editor, qtbot):
        """Tab indents every line of the selection"""
        editor.setPlainText("line 1\nline 2\nline 3")
        set_cursor_selection(editor, 0, 20)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Tab)
        assert editor.toPlainText() == "    line 1\n    line 2\n    line 3"


class TestBehaviorManagement:
    """Test adding, removing, and getting behaviors."""

    def test_add_behavior(self, editor, qtbot):
        """Test adding a new behavior to the editor."""
        from QCodeSitter.behaviors.overscroll import Overscroll

        # Remove Overscroll behavior first, then add it back
        editor.remove_behavior(Overscroll)
        assert editor.get_behavior(Overscroll) is None
        new = editor.add_behavior(Overscroll)
        assert isinstance(new, Overscroll)
        assert editor.get_behavior(Overscroll) is new

    def test_remove_behavior(self, editor, qtbot):
        """Test removing a behavior from the editor."""
        assert editor.get_behavior(SmartIndent) is not None
        removed = editor.remove_behavior(SmartIndent)
        assert removed is not None
        assert editor.get_behavior(SmartIndent) is None

    def test_replace_behavior(self, editor, qtbot):
        """Test adding a behavior replaces existing one of same type."""
        old_behavior = editor.get_behavior(SmartIndent)
        new = editor.add_behavior(SmartIndent)
        assert new is not old_behavior
        assert editor.get_behavior(SmartIndent) is new

    def test_get_nonexistent_behavior(self, bare_editor, qtbot):
        """Test getting a behavior that doesn't exist returns None."""
        assert bare_editor.get_behavior(LineNumber) is None

    def test_removed_behavior_stops_listening(self, editor, qtbot):
        """Test a removed behavior no longer reacts to the editor."""
        editor.remove_behavior(HighlightMatchingSelection)
        editor.setPlainText("foo foo")
        set_cursor_selection(editor, 0, 3)
        assert editor.selections("selection_highlight") == []

    def test_remove_syntax_highlighting_clears_formats(self, editor, qtbot):
        """Test removing syntax highlighting removes its formats."""
        editor.setPlainText("def foo():\n    return 1\n")
        block = editor.document().firstBlock()
        assert block.layout().formats()
        editor.remove_behavior(SyntaxHighlighting)
        assert not block.layout().formats()


class TestAutoBracketWithMultiCursor:
    """Test auto-bracket behavior with multiple cursors."""

    def test_insert_pairs_at_all_cursors(self, editor, qtbot):
        """Test bracket pairs inserted at all cursors."""
        editor.setPlainText("a\nb\nc")
        # Cursors after each letter
        editor.cursors.replace_all(
            [CursorState(1, 1), CursorState(3, 3), CursorState(5, 5)]
        )
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "a()\nb()\nc()"
        assert get_cursor_positions(editor) == [2, 6, 10]

    def test_wrap_selections_at_all_cursors(self, editor, qtbot):
        """Test wrapping selections with brackets at all cursors."""
        editor.setPlainText("foo\nbar\nbaz")
        editor.cursors.replace_all(
            [CursorState(0, 3), CursorState(4, 7), CursorState(8, 11)]
        )
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "(foo)\n(bar)\n(baz)"


class TestSmartIndentWithMultiCursor:
    """Test smart indent behavior with multiple cursors."""

    def test_indent_all_lines_at_cursors(self, editor, qtbot):
        """Test indenting lines at all cursor positions."""
        editor.setPlainText("a\nb\nc")
        editor.cursors.replace_all(
            [CursorState(0, 0), CursorState(2, 2), CursorState(4, 4)]
        )
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Tab)
        assert editor.toPlainText() == "    a\n    b\n    c"

    def test_newline_preserves_indent_all_cursors(self, editor, qtbot):
        """Test newline maintains indent at all cursor positions."""
        editor.setPlainText("    a\n    b")
        # Cursors at the end of each line
        editor.cursors.replace_all([CursorState(5, 5), CursorState(11, 11)])
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "    a\n    \n    b\n    "


class TestOverscroll:
    def test_last_line_can_scroll_to_the_top(self, editor):
        editor.setPlainText("x\n" * 100)
        scrollbar = editor.verticalScrollBar()
        assert scrollbar.maximum() == editor.document().blockCount() - 1

    def test_keeps_scroll_position_when_qt_resets_the_range(self, editor, qtbot):
        editor.setPlainText("x\n" * 100)
        scrollbar = editor.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        # Resizing makes Qt recompute the normal scroll range
        editor.resize(editor.width(), editor.height() + 40)
        qtbot.wait(10)
        assert scrollbar.maximum() == editor.document().blockCount() - 1
        assert scrollbar.value() == scrollbar.maximum()

    def test_remove_restores_normal_range(self, editor):
        editor.setPlainText("x\n" * 100)
        scrollbar = editor.verticalScrollBar()
        extended = scrollbar.maximum()
        editor.remove_behavior(Overscroll)
        assert scrollbar.maximum() < extended

    def test_shades_below_the_document(self, editor):
        editor.setPlainText("x")
        image = editor.viewport().grab().toImage()
        bottom = image.pixelColor(5, image.height() - 5)
        assert bottom == editor.get_behavior(Overscroll)._brush.color()
