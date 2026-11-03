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
from QCodeSitter.behaviors.line_numbers import LineNumbers
from QCodeSitter.behaviors.overscroll import Overscroll
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.behaviors.tab_completion import TabCompletion
from QCodeSitter.cursors.state import CursorState
from tests.helpers import (
    get_cursor_positions,
    set_cursor_position,
    set_cursor_selection,
    simulate_keypress,
)


class TestAutoBracket:
    def test_insert_parentheses_pair(self, editor):
        editor.setPlainText("")
        simulate_keypress(editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "()"
        # Cursor should be between the parens
        assert editor.textCursor().position() == 1

    def test_insert_bracket_pair(self, editor):
        editor.setPlainText("")
        simulate_keypress(editor, QtCore.Qt.Key.Key_BracketLeft, "[")
        assert editor.toPlainText() == "[]"
        assert editor.textCursor().position() == 1

    def test_insert_brace_pair(self, editor):
        editor.setPlainText("")
        simulate_keypress(editor, QtCore.Qt.Key.Key_BraceLeft, "{")
        assert editor.toPlainText() == "{}"
        assert editor.textCursor().position() == 1

    def test_insert_quote_pair(self, editor):
        editor.setPlainText("")
        simulate_keypress(editor, QtCore.Qt.Key.Key_QuoteDbl, '"')
        assert editor.toPlainText() == '""'
        assert editor.textCursor().position() == 1

    def test_insert_single_quote_pair(self, editor):
        editor.setPlainText("")
        simulate_keypress(editor, QtCore.Qt.Key.Key_Apostrophe, "'")
        assert editor.toPlainText() == "''"
        assert editor.textCursor().position() == 1

    def test_apostrophe_inside_a_word_is_not_paired(self, editor):
        editor.setPlainText("# don")
        set_cursor_position(editor, 5)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Apostrophe, "'")
        assert editor.toPlainText() == "# don'"
        assert editor.textCursor().position() == 6

    def test_quote_after_a_string_prefix_is_paired(self, editor):
        editor.setPlainText("x = f")
        set_cursor_position(editor, 5)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Apostrophe, "'")
        assert editor.toPlainText() == "x = f''"
        assert editor.textCursor().position() == 6

    def test_skip_closing_paren(self, editor):
        editor.setPlainText("()")
        set_cursor_position(editor, 1)  # Between parens
        simulate_keypress(editor, QtCore.Qt.Key.Key_ParenRight, ")")
        assert editor.toPlainText() == "()"
        assert editor.textCursor().position() == 2

    def test_skip_closing_bracket(self, editor):
        editor.setPlainText("[]")
        set_cursor_position(editor, 1)
        simulate_keypress(editor, QtCore.Qt.Key.Key_BracketRight, "]")
        assert editor.toPlainText() == "[]"
        assert editor.textCursor().position() == 2

    def test_skip_closing_quote(self, editor):
        editor.setPlainText('""')
        set_cursor_position(editor, 1)
        simulate_keypress(editor, QtCore.Qt.Key.Key_QuoteDbl, '"')
        assert editor.toPlainText() == '""'
        assert editor.textCursor().position() == 2

    def test_wrap_selection_with_parens(self, editor):
        editor.setPlainText("hello")
        set_cursor_selection(editor, 0, 5)
        simulate_keypress(editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "(hello)"

    def test_wrap_selection_with_quotes(self, editor):
        editor.setPlainText("x = hello")
        set_cursor_selection(editor, 4, 9)
        simulate_keypress(editor, QtCore.Qt.Key.Key_QuoteDbl, '"')
        assert editor.toPlainText() == 'x = "hello"'
        cursor = editor.textCursor()
        assert (cursor.selectionStart(), cursor.selectionEnd()) == (5, 10)

    def test_pairs_option(self, editor):
        """The auto_bracket_pairs option changes which pairs are inserted"""
        editor.options["auto_bracket_pairs"] = ["()"]
        editor.setPlainText("")
        simulate_keypress(editor, QtCore.Qt.Key.Key_BracketLeft, "[")
        assert editor.toPlainText() == "["

    def test_delete_pair(self, editor):
        editor.setPlainText("()")
        set_cursor_position(editor, 1)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_delete_quote_pair(self, editor):
        editor.setPlainText('""')
        set_cursor_position(editor, 1)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_no_delete_pair_with_content(self, editor):
        editor.setPlainText("(x)")
        set_cursor_position(editor, 2)  # After 'x'
        simulate_keypress(editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == "()"

    def test_ctrl_backspace_deletes_a_word_not_the_pair(self, editor):
        editor.setPlainText("foo()")
        set_cursor_position(editor, 4)
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_Backspace,
            "",
            QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "foo)"


class TestSmartIndent:
    @pytest.mark.parametrize(
        "line", ["def foo():", "if True:", "for i in range(10):", "x = ["]
    )
    def test_indent_after_block_opener(self, editor, line):
        """Enter after a line that opens a block indents the new line"""
        editor.setPlainText(line)
        set_cursor_position(editor, len(line))
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == line + "\n    "

    def test_dedent_after_return(self, editor):
        editor.setPlainText("def foo():\n    return 1")
        set_cursor_position(editor, len(editor.toPlainText()))
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "def foo():\n    return 1\n"

    def test_maintain_indent(self, editor):
        editor.setPlainText("    x = 1")
        set_cursor_position(editor, 9)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "    x = 1\n    "

    def test_newline_at_start_of_indented_line(self, editor):
        """Enter at column 0 moves the line down without adding indent"""
        editor.setPlainText("    x = 1\n    y = 2")
        set_cursor_position(editor, 10)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "    x = 1\n\n    y = 2"
        assert editor.textCursor().position() == 11

    def test_newline_at_start_of_blank_indented_line(self, editor):
        editor.setPlainText("    x = 1\n    ")
        set_cursor_position(editor, 10)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "    x = 1\n\n    "

    def test_tab_inserts_spaces(self, editor):
        editor.setPlainText("")
        simulate_keypress(editor, QtCore.Qt.Key.Key_Tab)
        assert editor.toPlainText() == "    "

    def test_shift_tab_unindents(self, editor):
        editor.setPlainText("    hello")
        set_cursor_position(editor, 4)
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_Backtab,
            modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        text = editor.toPlainText()
        assert text == "hello"

    def test_shift_tab_unindents_tabs_over_blank_line(self, editor):
        editor.options["indent_using_tabs"] = True
        editor.setPlainText("\ta\n\n\tb")
        set_cursor_selection(editor, 0, 6)
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_Backtab,
            modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        assert editor.toPlainText() == "a\n\nb"

    def test_smart_backspace_removes_indent(self, editor):
        editor.setPlainText("    ")
        set_cursor_position(editor, 4)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_newline_between_brackets(self, editor):
        """Enter between brackets puts the closing bracket below an indented line"""
        editor.setPlainText("    x = []")
        set_cursor_position(editor, 9)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        assert editor.toPlainText() == "    x = [\n        \n    ]"
        # The cursor is on the indented line
        assert editor.textCursor().position() == len("    x = [\n        ")

    def test_closing_bracket_dedent(self, editor):
        """A closing bracket typed on a blank line removes one indent"""
        editor.setPlainText("def foo():\n        ")
        set_cursor_position(editor, 19)  # End of indented line
        simulate_keypress(editor, QtCore.Qt.Key.Key_ParenRight, ")")
        assert editor.toPlainText() == "def foo():\n    )"

    def test_tab_indents_selection(self, editor):
        """Tab indents every line of the selection"""
        editor.setPlainText("line 1\nline 2\nline 3")
        set_cursor_selection(editor, 0, 20)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Tab)
        assert editor.toPlainText() == "    line 1\n    line 2\n    line 3"


class TestBehaviorManagement:
    def test_add_behavior(self, editor):
        from QCodeSitter.behaviors.overscroll import Overscroll

        # Remove Overscroll behavior first, then add it back
        editor.remove_behavior(Overscroll)
        assert editor.get_behavior(Overscroll) is None
        new = editor.add_behavior(Overscroll)
        assert isinstance(new, Overscroll)
        assert editor.get_behavior(Overscroll) is new

    def test_remove_behavior(self, editor):
        assert editor.get_behavior(SmartIndent) is not None
        removed = editor.remove_behavior(SmartIndent)
        assert removed is not None
        assert editor.get_behavior(SmartIndent) is None

    def test_replace_behavior(self, editor):
        old_behavior = editor.get_behavior(SmartIndent)
        new = editor.add_behavior(SmartIndent)
        assert new is not old_behavior
        assert editor.get_behavior(SmartIndent) is new

    def test_get_nonexistent_behavior(self, bare_editor):
        assert bare_editor.get_behavior(LineNumbers) is None

    def test_get_behavior_finds_subclasses(self, bare_editor):
        class MyHighlighting(SyntaxHighlighting):
            pass

        behavior = bare_editor.add_behavior(MyHighlighting)
        assert bare_editor.get_behavior(SyntaxHighlighting) is behavior
        assert bare_editor.get_behavior(MyHighlighting) is behavior

    def test_registry_matches_subclasses(self, editor):
        editor.remove_behavior(TabCompletion)

        class MyCompletion(TabCompletion):
            pass

        mine = editor.add_behavior(MyCompletion)
        assert editor.get_behavior(TabCompletion) is mine
        assert editor.remove_behavior(TabCompletion) is mine
        assert editor.get_behavior(TabCompletion) is None

        # Adding the base type replaces an installed subclass
        editor.add_behavior(MyCompletion)
        plain = editor.add_behavior(TabCompletion)
        assert type(plain) is TabCompletion
        assert editor.get_behavior(MyCompletion) is None

    def test_indent_commands_work_outside_key_presses(self, editor):
        editor.setPlainText("a\nb")
        set_cursor_selection(editor, 0, 3)
        smart_indent = editor.get_behavior(SmartIndent)
        smart_indent.insert_indent()
        assert editor.toPlainText() == "    a\n    b"
        smart_indent.unindent()
        assert editor.toPlainText() == "a\nb"

    def test_removed_behavior_stops_listening(self, editor):
        editor.remove_behavior(HighlightMatchingSelection)
        editor.setPlainText("foo foo")
        set_cursor_selection(editor, 0, 3)
        assert editor.selections("selection_highlight") == []

    def test_remove_syntax_highlighting_clears_formats(self, editor):
        editor.setPlainText("def foo():\n    return 1\n")
        block = editor.document().firstBlock()
        assert block.layout().formats()
        editor.remove_behavior(SyntaxHighlighting)
        assert not block.layout().formats()


class TestAutoBracketWithMultiCursor:
    def test_insert_pairs_at_all_cursors(self, editor):
        editor.setPlainText("a\nb\nc")
        # Cursors after each letter
        editor.cursors.replace_all(
            [CursorState(1, 1), CursorState(3, 3), CursorState(5, 5)]
        )
        simulate_keypress(editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "a()\nb()\nc()"
        assert get_cursor_positions(editor) == [2, 6, 10]

    def test_wrap_selections_at_all_cursors(self, editor):
        editor.setPlainText("foo\nbar\nbaz")
        editor.cursors.replace_all(
            [CursorState(0, 3), CursorState(4, 7), CursorState(8, 11)]
        )
        simulate_keypress(editor, QtCore.Qt.Key.Key_ParenLeft, "(")
        assert editor.toPlainText() == "(foo)\n(bar)\n(baz)"


class TestSmartIndentWithMultiCursor:
    def test_indent_all_lines_at_cursors(self, editor):
        editor.setPlainText("a\nb\nc")
        editor.cursors.replace_all(
            [CursorState(0, 0), CursorState(2, 2), CursorState(4, 4)]
        )
        simulate_keypress(editor, QtCore.Qt.Key.Key_Tab)
        assert editor.toPlainText() == "    a\n    b\n    c"

    def test_newline_preserves_indent_all_cursors(self, editor):
        editor.setPlainText("    a\n    b")
        # Cursors at the end of each line
        editor.cursors.replace_all([CursorState(5, 5), CursorState(11, 11)])
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
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
        with qtbot.waitSignal(scrollbar.rangeChanged, timeout=1000):
            editor.resize(editor.width(), editor.height() + 40)
        assert scrollbar.maximum() == editor.document().blockCount() - 1
        assert scrollbar.value() == scrollbar.maximum()

    def test_remove_restores_normal_range(self, editor):
        editor.setPlainText("x\n" * 100)
        scrollbar = editor.verticalScrollBar()
        extended = scrollbar.maximum()
        editor.remove_behavior(Overscroll)
        assert scrollbar.maximum() < extended

    def test_remove_with_a_short_document(self, editor):
        editor.setPlainText("x")
        scrollbar = editor.verticalScrollBar()
        editor.remove_behavior(Overscroll)
        assert scrollbar.minimum() == 0
        assert scrollbar.maximum() >= 0

    def test_shades_below_the_document(self, editor):
        editor.options["colors"] = {**editor.options["colors"], "outside_bg": "#123456"}
        editor.setPlainText("x")
        image = editor.viewport().grab().toImage()
        bottom = image.pixelColor(5, image.height() - 5)
        assert bottom.name() == "#123456"


class TestHighlightMatchingSelection:
    def ranges(self, editor) -> list[tuple[int, int]]:
        return [
            (s.cursor.selectionStart(), s.cursor.selectionEnd())
            for s in editor.selections(HighlightMatchingSelection.SOURCE)
        ]

    def test_highlights_the_other_occurrences(self, editor):
        editor.setPlainText("foo bar foo baz foo")
        set_cursor_selection(editor, 8, 11)
        # Not the selection itself, which Qt already highlights
        assert self.ranges(editor) == [(0, 3), (16, 19)]

    def test_skips_a_backward_selection_itself(self, editor):
        editor.setPlainText("foo bar foo")
        set_cursor_selection(editor, 3, 0)
        assert self.ranges(editor) == [(8, 11)]

    def test_matches_case(self, editor):
        editor.setPlainText("foo Foo foo")
        set_cursor_selection(editor, 0, 3)
        assert self.ranges(editor) == [(8, 11)]

    def test_clears_when_the_selection_goes(self, editor):
        editor.setPlainText("foo foo")
        set_cursor_selection(editor, 0, 3)
        assert self.ranges(editor) == [(4, 7)]
        set_cursor_position(editor, 1)
        assert self.ranges(editor) == []

    @pytest.mark.parametrize("length", [1, HighlightMatchingSelection.MAX_LENGTH + 1])
    def test_length_limits(self, editor, length):
        word = "a" * length
        editor.setPlainText(f"{word} {word}")
        set_cursor_selection(editor, 0, length)
        assert self.ranges(editor) == []
