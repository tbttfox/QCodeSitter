"""
Integration tests for core CodeEditor functionality.

Tests basic text operations, cursor movement, clipboard operations,
and document management.
"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.code_editor import CursorState

from tests.helpers import (
    set_cursor_position,
    set_cursor_selection,
    simulate_keypress,
)


class TestEditorBasicOperations:
    """Test basic text insertion and deletion."""

    def test_insert_text(self, editor, qtbot):
        """Test inserting text at cursor position via keypress."""
        editor.setPlainText("")
        for char in "Hello":
            simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_H, char)
        assert editor.toPlainText() == "Hello"

    def test_insert_text_at_position(self, editor, qtbot):
        """Test inserting text at a specific position."""
        editor.setPlainText("Hello World")
        set_cursor_position(editor, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Comma, ",")
        assert editor.toPlainText() == "Hello, World"

    def test_backspace(self, editor, qtbot):
        """Test backspace deletes character before cursor."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == "Hell"

    def test_backspace_at_start(self, editor, qtbot):
        """Test backspace at document start does nothing."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 0)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == "Hello"

    def test_delete_char(self, editor, qtbot):
        """Test delete removes character after cursor."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 0)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Delete)
        assert editor.toPlainText() == "ello"

    def test_delete_at_end(self, editor, qtbot):
        """Test delete at document end does nothing."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Delete)
        assert editor.toPlainText() == "Hello"

    def test_delete_selection(self, editor, qtbot):
        """Test deleting selected text."""
        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 0, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == " World"

    def test_insert_newline(self, editor, qtbot):
        """Test inserting a newline."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)
        assert "Hello\n" in editor.toPlainText()

    def test_replace_selection(self, editor, qtbot):
        """Test typing replaces selected text."""
        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 6, 11)
        # Type "Python" to replace "World"
        for char in "Python":
            simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_P, char)
        assert editor.toPlainText() == "Hello Python"


class TestCursorMovement:
    """Test cursor navigation."""

    def test_move_left(self, editor, qtbot):
        """Test moving cursor left."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 3)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Left)
        assert editor.textCursor().position() == 2

    def test_move_right(self, editor, qtbot):
        """Test moving cursor right."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 2)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Right)
        assert editor.textCursor().position() == 3

    def test_move_up(self, editor, qtbot):
        """Test moving cursor up a line."""
        editor.setPlainText("Line 1\nLine 2")
        set_cursor_position(editor, 10)  # Middle of line 2
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Up)
        cursor = editor.textCursor()
        assert cursor.blockNumber() == 0

    def test_move_down(self, editor, qtbot):
        """Test moving cursor down a line."""
        editor.setPlainText("Line 1\nLine 2")
        set_cursor_position(editor, 3)  # Middle of line 1
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Down)
        cursor = editor.textCursor()
        assert cursor.blockNumber() == 1

    def test_move_home(self, editor, qtbot):
        """Test Home key moves to start of line."""
        editor.setPlainText("    Hello")
        set_cursor_position(editor, 8)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Home)
        # Smart home should go to first non-whitespace
        assert editor.textCursor().position() == 4

    def test_move_home_toggle(self, editor, qtbot):
        """Test Home key toggles between first non-ws and column 0."""
        editor.setPlainText("    Hello")
        set_cursor_position(editor, 4)  # At first non-ws
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Home)
        assert editor.textCursor().position() == 0

    def test_move_end(self, editor, qtbot):
        """Test End key moves to end of line."""
        editor.setPlainText("Hello\nWorld")
        set_cursor_position(editor, 0)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_End)
        assert editor.textCursor().position() == 5

    def test_move_word_right(self, editor, qtbot):
        """Test Ctrl+Right moves to next word."""
        editor.setPlainText("Hello World")
        set_cursor_position(editor, 0)
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Right,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Should be at or past "Hello"
        assert editor.textCursor().position() >= 5

    def test_move_word_left(self, editor, qtbot):
        """Test Ctrl+Left moves to previous word."""
        editor.setPlainText("Hello World")
        set_cursor_position(editor, 11)
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Left,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Should be at start of "World"
        assert editor.textCursor().position() <= 6

    def test_select_with_shift(self, editor, qtbot):
        """Test Shift+arrow creates selection."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 0)
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Right,
            modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier,
        )
        cursor = editor.textCursor()
        assert cursor.hasSelection()
        assert cursor.selectedText() == "H"


class TestClipboardOperations:
    """Test copy, cut, and paste operations."""

    def test_copy_selection(self, editor, qtbot):
        """Test copying selected text."""
        from Qt import QtWidgets

        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 0, 5)
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_C,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        clipboard = QtWidgets.QApplication.clipboard()
        assert clipboard.text() == "Hello"

    def test_cut_selection(self, editor, qtbot):
        """Test cutting selected text."""
        from Qt import QtWidgets

        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 0, 6)
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_X,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "World"
        clipboard = QtWidgets.QApplication.clipboard()
        assert clipboard.text() == "Hello "

    def test_paste_text(self, editor, qtbot):
        """Test pasting text from clipboard."""
        from Qt import QtWidgets

        editor.setPlainText("")
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText("Pasted")
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_V,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "Pasted"

    def test_paste_replaces_selection(self, editor, qtbot):
        """Test pasting replaces selected text."""
        from Qt import QtWidgets

        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 6, 11)
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText("Python")
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_V,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "Hello Python"


class TestUndoRedo:
    """Test undo and redo operations."""

    def test_undo_insertion(self, editor, qtbot):
        """Test undo reverses text insertion."""
        editor.setPlainText("")
        # Type "Hello" via keypresses
        for char in "Hello":
            simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_H, char)
        assert editor.toPlainText() == "Hello"
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Z,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        # Undo may undo all or part depending on edit block merging
        assert len(editor.toPlainText()) < 5

    def test_redo_insertion(self, editor, qtbot):
        """Test redo restores undone insertion."""
        editor.setPlainText("")
        # Type a single character to make undo/redo predictable
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_X, "X")
        assert editor.toPlainText() == "X"
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Z,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == ""
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Y,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "X"

    def test_undo_deletion(self, editor, qtbot):
        """Test undo reverses deletion."""
        editor.setPlainText("Hello")
        set_cursor_position(editor, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Backspace)
        assert editor.toPlainText() == "Hell"
        simulate_keypress(
            qtbot,
            editor,
            QtCore.Qt.Key.Key_Z,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "Hello"


class TestDocumentState:
    """Test document state management."""

    def test_set_plain_text(self, editor):
        """Test setting document text."""
        editor.setPlainText("Test content")
        assert editor.toPlainText() == "Test content"

    def test_clear_document(self, editor):
        """Test clearing the document."""
        editor.setPlainText("Test content")
        editor.setPlainText("")
        assert editor.toPlainText() == ""

    def test_document_line_count(self, editor):
        """Test getting document line count."""
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        assert editor.document().blockCount() == 3

    def test_cursor_state_dataclass(self):
        """Test CursorState helper class."""
        state = CursorState(0, 5)
        assert state.anchor == 0
        assert state.position == 5
        assert state.hasSelection() is True
        assert state.selectionStart() == 0
        assert state.selectionEnd() == 5

    def test_cursor_state_no_selection(self):
        """Test CursorState without selection."""
        state = CursorState(5, 5)
        assert state.hasSelection() is False
        assert state.selectionStart() == 5
        assert state.selectionEnd() == 5

    def test_cursor_state_offset(self):
        """Test CursorState offset method."""
        state = CursorState(0, 5)
        state.offset(10)
        assert state.anchor == 10
        assert state.position == 15


class TestEscapeKey:
    """Test escape key behavior."""

    def test_escape_exits_multi_cursor(self, editor_with_multicursor, qtbot):
        """Test escape exits multi-cursor mode."""
        editor = editor_with_multicursor
        assert len(editor.secondary_cursors) == 2
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Escape)
        assert len(editor.secondary_cursors) == 0
