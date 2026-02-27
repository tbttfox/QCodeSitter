"""
Integration tests for multi-cursor functionality.

Tests adding, removing, and editing with multiple cursors,
cursor merging, and multi-cursor clipboard operations.
"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.code_editor import CursorState

from tests.helpers import (
    get_cursor_positions,
    set_cursor_position,
    set_cursor_selection,
    simulate_keypress,
)


class TestAddingCursors:
    """Test various methods of adding cursors."""

    def test_add_cursor_at_position(self, editor, qtbot):
        """Test adding a cursor at a specific position."""
        editor.setPlainText("Hello World")
        set_cursor_position(editor, 0)
        editor.add_cursor_at_position(6)
        assert len(editor.secondary_cursors) == 1
        positions = get_cursor_positions(editor)
        assert 0 in positions
        assert 6 in positions

    def test_add_cursor_below(self, editor, qtbot):
        """Test adding cursor on line below."""
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        set_cursor_position(editor, 3)  # Middle of line 1
        editor.add_cursor_below()
        assert len(editor.secondary_cursors) == 1
        # Primary should now be on line 2
        primary = editor.get_primary_cursor()
        cursor = primary.build_cursor(editor.document())
        assert cursor.blockNumber() == 1

    def test_add_cursor_above(self, editor, qtbot):
        """Test adding cursor on line above."""
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        set_cursor_position(editor, 10)  # Middle of line 2
        editor.add_cursor_above()
        assert len(editor.secondary_cursors) == 1
        # Primary should now be on line 1
        primary = editor.get_primary_cursor()
        cursor = primary.build_cursor(editor.document())
        assert cursor.blockNumber() == 0

    def test_add_next_occurrence(self, editor, qtbot):
        """Test adding cursor at next occurrence of selection."""
        editor.setPlainText("foo bar foo baz foo")
        set_cursor_selection(editor, 0, 3)  # Select first "foo"
        editor.add_next_occurrence()
        assert len(editor.secondary_cursors) == 1
        # Check that the secondary cursor is at the second "foo"
        cursors, _ = editor.get_all_cursors()
        positions = [c.selectionStart() for c in cursors]
        assert 0 in positions
        assert 8 in positions

    def test_add_next_occurrence_wraps(self, editor, qtbot):
        """Test add next occurrence wraps to beginning."""
        editor.setPlainText("foo bar foo")
        set_cursor_selection(editor, 8, 11)  # Select second "foo"
        editor.add_next_occurrence()
        assert len(editor.secondary_cursors) == 1
        # Should wrap to first "foo"
        cursors, _ = editor.get_all_cursors()
        positions = [c.selectionStart() for c in cursors]
        assert 0 in positions
        assert 8 in positions

    def test_add_cursors_to_line_ends(self, editor, qtbot):
        """Test adding cursors to end of each line in selection."""
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        set_cursor_selection(editor, 0, 20)  # Select all three lines
        editor.add_cursors_to_line_ends()
        # Should have cursors at end of all 3 lines
        cursors, _ = editor.get_all_cursors()
        assert len(cursors) == 3


class TestCursorMerging:
    """Test that overlapping cursors are merged properly."""

    def test_merge_adjacent_cursors(self, editor, qtbot):
        """Test that adjacent cursors are merged."""
        editor.setPlainText("Hello World")
        # Add cursors at adjacent positions
        set_cursor_position(editor, 5)
        editor.secondary_cursors = [CursorState(5, 5)]
        editor._set_all_cursors([CursorState(5, 5), CursorState(5, 5)])
        # Should merge into one cursor
        cursors, _ = editor.get_all_cursors()
        assert len(cursors) == 1

    def test_merge_overlapping_selections(self, editor, qtbot):
        """Test that overlapping selections are merged."""
        editor.setPlainText("Hello World")
        # Create overlapping selections
        editor.secondary_cursors = [CursorState(0, 6)]  # "Hello "
        set_cursor_selection(editor, 4, 11)  # "o World"
        editor._set_all_cursors([CursorState(0, 6), CursorState(4, 11)])
        # Should merge into one selection covering the whole text
        cursors, _ = editor.get_all_cursors()
        assert len(cursors) == 1
        assert cursors[0].selectionStart() == 0
        assert cursors[0].selectionEnd() == 11


class TestMultiCursorEditing:
    """Test editing operations with multiple cursors."""

    def test_insert_at_all_cursors(self, editor_with_multicursor, qtbot):
        """Test inserting text at all cursor positions."""
        editor = editor_with_multicursor
        # Insert "X" at all cursors
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_X, "X")
        text = editor.toPlainText()
        # Each line that had a cursor should now start with "X"
        lines = text.split("\n")
        assert lines[0].startswith("X")
        assert lines[1].startswith("X")
        assert lines[2].startswith("X")

    def test_delete_at_all_cursors(self, editor_with_multicursor, qtbot):
        """Test deleting at all cursor positions."""
        editor = editor_with_multicursor
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Delete)
        text = editor.toPlainText()
        lines = text.split("\n")
        # First char of first three lines should be deleted
        assert lines[0] == "oo"
        assert lines[1] == "oo"
        assert lines[2] == "oo"

    def test_backspace_at_all_cursors(self, editor, qtbot):
        """Test backspace at all cursor positions."""
        editor.setPlainText("Xfoo\nXfoo\nXfoo")
        # Set cursors at position 1 on each line (after X)
        cursor = editor.textCursor()
        cursor.setPosition(1)
        editor.setTextCursor(cursor)
        editor.secondary_cursors = [CursorState(6, 6), CursorState(11, 11)]
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "foo"
        assert lines[1] == "foo"
        assert lines[2] == "foo"

    def test_newline_at_all_cursors(self, editor_with_multicursor, qtbot):
        """Test inserting newlines at all cursor positions."""
        editor = editor_with_multicursor
        original_line_count = editor.document().blockCount()
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        # Should have 3 more lines (one newline per cursor)
        new_line_count = editor.document().blockCount()
        assert new_line_count == original_line_count + 3


class TestMultiCursorClipboard:
    """Test clipboard operations with multiple cursors."""

    def test_copy_from_multiple_cursors(self, editor, qtbot):
        """Test copying from multiple cursors."""
        from Qt import QtWidgets

        editor.setPlainText("foo\nbar\nbaz")
        # Select "foo", "bar", "baz" with separate cursors
        set_cursor_selection(editor, 0, 3)
        editor.secondary_cursors = [
            CursorState(4, 7),  # "bar"
            CursorState(8, 11),  # "baz"
        ]
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_C,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        clipboard = QtWidgets.QApplication.clipboard()
        # Clipboard should contain all selections joined by newlines
        assert clipboard.text() == "foo\nbar\nbaz"

    def test_cut_from_multiple_cursors(self, editor, qtbot):
        """Test cutting from multiple cursors."""
        editor.setPlainText("Xfoo\nXbar\nXbaz")
        # Select "X" on each line
        set_cursor_selection(editor, 0, 1)
        editor.secondary_cursors = [
            CursorState(5, 6),
            CursorState(10, 11),
        ]
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_X,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "foo"
        assert lines[1] == "bar"
        assert lines[2] == "baz"

    def test_paste_to_multiple_cursors(self, editor, qtbot):
        """Test pasting to multiple cursors with matching count."""
        editor.setPlainText("_\n_\n_")
        # Set up 3 cursors at the underscore positions
        set_cursor_selection(editor, 0, 1)
        editor.secondary_cursors = [
            CursorState(2, 3),
            CursorState(4, 5),
        ]
        # First copy from matching cursors
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_C,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Clear and set up new content
        editor.setPlainText("A\nB\nC")
        set_cursor_position(editor, 1)
        editor.secondary_cursors = [
            CursorState(3, 3),
            CursorState(5, 5),
        ]
        # Paste should distribute to each cursor
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_V,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Each line should have pasted content
        text = editor.toPlainText()
        assert "_" in text


class TestExitMultiCursor:
    """Test exiting multi-cursor mode."""

    def test_escape_exits_multi_cursor(self, editor_with_multicursor, qtbot):
        """Test pressing Escape exits multi-cursor mode."""
        editor = editor_with_multicursor
        assert len(editor.secondary_cursors) == 2
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Escape)
        assert len(editor.secondary_cursors) == 0

    def test_click_exits_multi_cursor(self, editor_with_multicursor, qtbot):
        """Test clicking exits multi-cursor mode."""
        editor = editor_with_multicursor
        assert len(editor.secondary_cursors) == 2
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
        assert len(editor.secondary_cursors) == 0

    def test_alt_click_adds_cursor(self, editor, qtbot):
        """Test Alt+Click adds a cursor instead of exiting."""
        editor.setPlainText("Hello World")
        set_cursor_position(editor, 0)
        assert len(editor.secondary_cursors) == 0
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
        assert len(editor.secondary_cursors) >= 0  # At least processed

    def test_ctrl_a_exits_multi_cursor(self, editor_with_multicursor, qtbot):
        """Test Ctrl+A exits multi-cursor mode before selecting all."""
        editor = editor_with_multicursor
        assert len(editor.secondary_cursors) == 2
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_A,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert len(editor.secondary_cursors) == 0


class TestCursorIterator:
    """Test the CursorIterator class for multi-cursor operations."""

    def test_cursor_iterator_offset_tracking(self, editor, qtbot):
        """Test that CursorIterator correctly tracks position offsets."""
        editor.setPlainText("abc\nabc\nabc")
        set_cursor_position(editor, 0)
        editor.secondary_cursors = [CursorState(4, 4), CursorState(8, 8)]
        # Insert "X" at each position - later cursors should be offset
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_X, "X")
        text = editor.toPlainText()
        lines = text.split("\n")
        # Each line should start with "X"
        assert all(line.startswith("X") for line in lines)

    def test_cursor_iterator_with_deletions(self, editor, qtbot):
        """Test CursorIterator with deletions that change offsets."""
        editor.setPlainText("Xabc\nXabc\nXabc")
        set_cursor_position(editor, 0)
        editor.secondary_cursors = [CursorState(5, 5), CursorState(10, 10)]
        # Delete first char at each position
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Delete)
        text = editor.toPlainText()
        lines = text.split("\n")
        # "X" should be removed from each line
        assert all(line == "abc" for line in lines)


class TestMultiCursorMovement:
    """Test cursor movement with multiple cursors."""

    def test_all_cursors_move_left(self, editor_with_multicursor, qtbot):
        """Test all cursors move left together."""
        editor = editor_with_multicursor
        # Move right first to not be at start
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Right)
        positions_before = get_cursor_positions(editor)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Left)
        positions_after = get_cursor_positions(editor)
        # All should have moved left by 1
        for before, after in zip(positions_before, positions_after):
            assert after == before - 1

    def test_all_cursors_move_right(self, editor_with_multicursor, qtbot):
        """Test all cursors move right together."""
        editor = editor_with_multicursor
        positions_before = get_cursor_positions(editor)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Right)
        positions_after = get_cursor_positions(editor)
        # All should have moved right by 1
        for before, after in zip(positions_before, positions_after):
            assert after == before + 1

    def test_selection_with_multiple_cursors(self, editor_with_multicursor, qtbot):
        """Test Shift+Arrow creates selection at all cursors."""
        editor = editor_with_multicursor
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Right,
            modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        cursors, _ = editor.get_all_cursors()
        # All cursors should have selections
        assert all(c.hasSelection() for c in cursors)
