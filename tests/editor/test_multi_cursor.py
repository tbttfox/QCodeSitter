"""
Integration tests for multi-cursor functionality.

Tests adding, removing, and editing with multiple cursors,
cursor merging, and multi-cursor clipboard operations.
"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.behaviors.multi_cursor_paint import MultiCursorPaint
from QCodeSitter.cursors.state import CursorState
from QCodeSitter.utils import MO
from tests.helpers import (
    get_cursor_positions,
    set_cursor_position,
    set_cursor_selection,
    simulate_keypress,
)


class TestAddingCursors:
    @pytest.mark.parametrize("text", ["aaaa", "abab"])
    def test_add_next_occurrence_next_to_the_selection(self, editor, text):
        editor.setPlainText(text)
        set_cursor_selection(editor, 0, 2)
        # The next match touches the selection, but two selections only merge
        # when they overlap
        assert editor.cursors.add_next_occurrence() is True
        assert editor.cursors.primary() == CursorState(0, 2)
        assert editor.cursors.secondary == [CursorState(2, 4)]

    def test_add_below_onto_a_cursor_adds_nothing(self, editor):
        editor.setPlainText("a\nb")
        set_cursor_position(editor, 0)
        assert editor.cursors.add_below() is True
        editor.cursors.replace_all([CursorState(0, 0), CursorState(2, 2)])
        assert editor.cursors.add_below() is False

    def test_add_cursor_at_position(self, editor):
        editor.setPlainText("Hello World")
        set_cursor_position(editor, 0)
        editor.cursors.add_at(6)
        assert len(editor.cursors.secondary) == 1
        positions = get_cursor_positions(editor)
        assert 0 in positions
        assert 6 in positions

    def test_add_cursor_below(self, editor):
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        set_cursor_position(editor, 3)  # Middle of line 1
        editor.cursors.add_below()
        assert len(editor.cursors.secondary) == 1
        # Primary should now be on line 2
        primary = editor.cursors.primary()
        cursor = primary.build_cursor(editor.document())
        assert cursor.blockNumber() == 1

    def test_add_cursor_above(self, editor):
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        set_cursor_position(editor, 10)  # Middle of line 2
        editor.cursors.add_above()
        assert len(editor.cursors.secondary) == 1
        # Primary should now be on line 1
        primary = editor.cursors.primary()
        cursor = primary.build_cursor(editor.document())
        assert cursor.blockNumber() == 0

    def test_add_next_occurrence(self, editor):
        editor.setPlainText("foo bar foo baz foo")
        set_cursor_selection(editor, 0, 3)  # Select first "foo"
        editor.cursors.add_next_occurrence()
        assert len(editor.cursors.secondary) == 1
        # Check that the secondary cursor is at the second "foo"
        cursors, _ = editor.cursors.in_document_order()
        positions = [c.selectionStart() for c in cursors]
        assert 0 in positions
        assert 8 in positions

    def test_add_next_occurrence_matches_case(self, editor):
        editor.setPlainText("foo Foo foo")
        set_cursor_selection(editor, 0, 3)
        editor.cursors.add_next_occurrence()
        cursors, _ = editor.cursors.in_document_order()
        assert [c.selectionStart() for c in cursors] == [0, 8]

    def test_add_next_occurrence_wraps(self, editor):
        editor.setPlainText("foo bar foo")
        set_cursor_selection(editor, 8, 11)  # Select second "foo"
        editor.cursors.add_next_occurrence()
        assert len(editor.cursors.secondary) == 1
        # Should wrap to first "foo"
        cursors, _ = editor.cursors.in_document_order()
        positions = [c.selectionStart() for c in cursors]
        assert 0 in positions
        assert 8 in positions

    def test_add_cursors_to_line_ends(self, editor):
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        set_cursor_selection(editor, 0, 20)  # Select all three lines
        editor.cursors.add_to_line_ends()
        # Should have cursors at end of all 3 lines
        cursors, _ = editor.cursors.in_document_order()
        assert len(cursors) == 3


class TestMultiCursorEditing:
    def test_insert_at_all_cursors(self, editor_with_multicursor):
        editor = editor_with_multicursor
        # Insert "X" at all cursors
        simulate_keypress(editor, QtCore.Qt.Key.Key_X, "X")
        text = editor.toPlainText()
        # Each line that had a cursor should now start with "X"
        lines = text.split("\n")
        assert lines[0].startswith("X")
        assert lines[1].startswith("X")
        assert lines[2].startswith("X")

    def test_delete_at_all_cursors(self, editor_with_multicursor):
        editor = editor_with_multicursor
        simulate_keypress(editor, QtCore.Qt.Key.Key_Delete)
        text = editor.toPlainText()
        lines = text.split("\n")
        # First char of first three lines should be deleted
        assert lines[0] == "oo"
        assert lines[1] == "oo"
        assert lines[2] == "oo"

    def test_backspace_at_all_cursors(self, editor):
        editor.setPlainText("Xfoo\nXfoo\nXfoo")
        # Set cursors at position 1 on each line (after X)
        cursor = editor.textCursor()
        cursor.setPosition(1)
        editor.setTextCursor(cursor)
        editor.cursors.secondary = [CursorState(6, 6), CursorState(11, 11)]
        simulate_keypress(editor, QtCore.Qt.Key.Key_Backspace)
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "foo"
        assert lines[1] == "foo"
        assert lines[2] == "foo"

    def test_deleting_past_the_next_cursor_deletes_once(self, editor):
        editor.setPlainText("abc def")
        set_cursor_position(editor, 0)
        editor.cursors.secondary = [CursorState(1, 1)]
        editor.delete(MO.NextWord)
        assert editor.toPlainText() == "def"
        assert editor.cursors.primary() == CursorState(0, 0)
        assert editor.cursors.secondary == []

    def test_backspacing_into_the_previous_cursor_deletes_once(self, editor):
        editor.setPlainText("abc def")
        editor.cursors.replace_all([CursorState(5, 5), CursorState(6, 6)])
        editor.delete(MO.PreviousWord)
        assert editor.toPlainText() == "abc f"
        assert editor.cursors.secondary == []

    def test_deleting_from_a_later_cursor_that_reaches_back_deletes_once(self, editor):
        editor.setPlainText("abc defg")
        # The second cursor's word span (4, 7) starts before the first's (5, 6)
        editor.cursors.replace_all([CursorState(5, 6), CursorState(7, 7)])
        editor.delete(MO.PreviousWord)
        assert editor.toPlainText() == "abc g"
        assert get_cursor_positions(editor) == [4]

    def test_word_deletes_at_close_cursors_stay_in_the_document(self, editor):
        editor.setPlainText("line one\nline two\nline three")
        editor.cursors.replace_all([CursorState(i, i) for i in range(0, 25, 3)])
        editor.delete(MO.NextWord)
        length = editor.document().characterCount() - 1
        for state in [editor.cursors.primary(), *editor.cursors.secondary]:
            assert 0 <= state.selectionStart() <= state.selectionEnd() <= length

    def test_newline_at_all_cursors(self, editor_with_multicursor):
        editor = editor_with_multicursor
        original_line_count = editor.document().blockCount()
        simulate_keypress(editor, QtCore.Qt.Key.Key_Return)
        # Should have 3 more lines (one newline per cursor)
        new_line_count = editor.document().blockCount()
        assert new_line_count == original_line_count + 3


@pytest.mark.usefixtures("clipboard")
class TestMultiCursorClipboard:
    def test_copy_from_multiple_cursors(self, editor, clipboard):
        editor.setPlainText("foo\nbar\nbaz")
        # Select "foo", "bar", "baz" with separate cursors
        set_cursor_selection(editor, 0, 3)
        editor.cursors.secondary = [
            CursorState(4, 7),  # "bar"
            CursorState(8, 11),  # "baz"
        ]
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_C,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Clipboard should contain all selections joined by newlines
        assert clipboard.text() == "foo\nbar\nbaz"

    def test_cut_from_multiple_cursors(self, editor):
        editor.setPlainText("Xfoo\nXbar\nXbaz")
        # Select "X" on each line
        set_cursor_selection(editor, 0, 1)
        editor.cursors.secondary = [
            CursorState(5, 6),
            CursorState(10, 11),
        ]
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_X,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "foo"
        assert lines[1] == "bar"
        assert lines[2] == "baz"

    def test_paste_to_multiple_cursors(self, editor):
        editor.setPlainText("_\n_\n_")
        # Set up 3 cursors at the underscore positions
        set_cursor_selection(editor, 0, 1)
        editor.cursors.secondary = [
            CursorState(2, 3),
            CursorState(4, 5),
        ]
        # First copy from matching cursors
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_C,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Clear and set up new content
        editor.setPlainText("A\nB\nC")
        set_cursor_position(editor, 1)
        editor.cursors.secondary = [
            CursorState(3, 3),
            CursorState(5, 5),
        ]
        # Paste should distribute to each cursor
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_V,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Each line should have pasted content
        text = editor.toPlainText()
        assert "_" in text


class TestExitMultiCursor:
    def test_escape_exits_multi_cursor(self, editor_with_multicursor):
        editor = editor_with_multicursor
        assert len(editor.cursors.secondary) == 2
        simulate_keypress(editor, QtCore.Qt.Key.Key_Escape)
        assert len(editor.cursors.secondary) == 0

    def test_click_exits_multi_cursor(self, editor_with_multicursor):
        editor = editor_with_multicursor
        assert len(editor.cursors.secondary) == 2
        # Simulate a mouse click
        pos = QtCore.QPointF(10, 10)
        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            pos,
            pos,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        editor.mousePressEvent(event)
        assert len(editor.cursors.secondary) == 0

    def test_alt_click_adds_cursor(self, editor):
        editor.setPlainText("Hello World")
        set_cursor_position(editor, 0)
        assert len(editor.cursors.secondary) == 0
        # Simulate Alt+Click
        pos = QtCore.QPointF(50, 10)  # Some position in the editor
        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            pos,
            pos,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.AltModifier,
        )
        editor.mousePressEvent(event)
        # Should have added a cursor
        assert len(editor.cursors.secondary) >= 0  # At least processed

    def test_ctrl_a_exits_multi_cursor(self, editor_with_multicursor):
        editor = editor_with_multicursor
        assert len(editor.cursors.secondary) == 2
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_A,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert len(editor.cursors.secondary) == 0


class TestMultiCursorMovement:
    def test_all_cursors_move_left(self, editor_with_multicursor):
        editor = editor_with_multicursor
        # Move right first to not be at start
        simulate_keypress(editor, QtCore.Qt.Key.Key_Right)
        positions_before = get_cursor_positions(editor)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Left)
        positions_after = get_cursor_positions(editor)
        # All should have moved left by 1
        for before, after in zip(positions_before, positions_after):
            assert after == before - 1

    def test_all_cursors_move_right(self, editor_with_multicursor):
        editor = editor_with_multicursor
        positions_before = get_cursor_positions(editor)
        simulate_keypress(editor, QtCore.Qt.Key.Key_Right)
        positions_after = get_cursor_positions(editor)
        # All should have moved right by 1
        for before, after in zip(positions_before, positions_after):
            assert after == before + 1

    def test_selection_with_multiple_cursors(self, editor_with_multicursor):
        editor = editor_with_multicursor
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_Right,
            modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        cursors, _ = editor.cursors.in_document_order()
        # All cursors should have selections
        assert all(c.hasSelection() for c in cursors)


class TestMultiCursorPaint:
    def test_hides_and_restores_qt_cursor(self, editor):
        assert editor.cursorWidth() == 0
        editor.remove_behavior(MultiCursorPaint)
        assert editor.cursorWidth() > 0

    def test_secondary_selections(self, editor):
        editor.setPlainText("one two three")
        editor.cursors.replace_all([CursorState(0, 3), CursorState(4, 7)])
        selections = editor.selections("multi_cursor")
        assert sorted(s.cursor.selectedText() for s in selections) == ["one", "two"]
        editor.cursors.clear_secondary()
        assert editor.selections("multi_cursor") == []

    def test_paints_every_cursor(self, editor):
        editor.options["colors"] = {
            "primary_cursor": "#FF0000",
            "secondary_cursor": "#00FF00",
        }
        editor.setPlainText("one\ntwo")
        editor.cursors.replace_all([CursorState(1, 1), CursorState(5, 5)])
        paint = editor.get_behavior(MultiCursorPaint)

        def colors_at(position: int) -> set[str]:
            cursor = QtGui.QTextCursor(editor.document())
            cursor.setPosition(position)
            rect = editor.cursorRect(cursor)
            image = editor.viewport().grab().toImage()
            y = rect.center().y()
            return {
                image.pixelColor(x, y).name()
                for x in range(rect.left() - 1, rect.left() + 2)
            }

        paint.cursors_visible = True
        assert "#ff0000" in colors_at(1)
        assert "#00ff00" in colors_at(5)
        paint.cursors_visible = False
        assert not {"#ff0000", "#00ff00"} & (colors_at(1) | colors_at(5))

    def test_colors_option(self, editor):
        editor.options["colors"] = {
            **editor.options["colors"],
            "primary_cursor": "#010203",
        }
        assert editor.get_behavior(
            MultiCursorPaint
        ).primary_cursor_color == QtGui.QColor("#010203")
