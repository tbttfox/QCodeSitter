"""
Integration tests for core CodeEditor functionality.

Tests basic text operations, cursor movement, clipboard operations,
and document management.
"""

from __future__ import annotations

from Qt import QtCore, QtGui

from QCodeSitter.cursors.state import CursorState
from QCodeSitter.gui_colors import gui_color
from tests.helpers import (
    assert_tree_matches_fresh_parse,
    get_cursor_positions,
    set_cursor_position,
    set_cursor_selection,
    simulate_keypress,
)


def drop_event(
    editor, position: int, text: str, action=QtCore.Qt.DropAction.CopyAction
) -> tuple[QtGui.QDropEvent, QtCore.QMimeData]:
    """A drop of text at a document position, from outside the editor

    The event doesn't own its mime data, so keep the mime data alive with it
    """
    mime = QtCore.QMimeData()
    if text:
        mime.setText(text)
    cursor = QtGui.QTextCursor(editor.document())
    cursor.setPosition(position)
    point = editor.cursorRect(cursor).center()
    event = QtGui.QDropEvent(
        QtCore.QPointF(point),
        action,
        mime,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )
    return event, mime


class TestDrop:
    def test_drop_inserts_at_the_drop_point(self, editor):
        editor.setPlainText("hello world")
        editor.cursors.replace_all([CursorState(0, 0), CursorState(11, 11)])
        event, _mime = drop_event(editor, 6, "big ")
        editor.dropEvent(event)
        assert event.isAccepted()
        assert editor.toPlainText() == "hello big world"
        # The drop point becomes the only cursor, after the dropped text
        assert get_cursor_positions(editor) == [10]
        assert_tree_matches_fresh_parse(editor)

    def test_drop_without_text_is_ignored(self, editor):
        editor.setPlainText("hello")
        event, _mime = drop_event(editor, 2, "")
        editor.dropEvent(event)
        assert not event.isAccepted()
        assert editor.toPlainText() == "hello"


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

    def test_insert_text_method_uses_current_cursor(self, editor, qtbot):
        """Test calling insert_text directly edits at the current cursor."""
        editor.setPlainText("abc")
        set_cursor_position(editor, 3)
        editor.insert_text("X")
        set_cursor_position(editor, 0)
        editor.insert_text("Y")
        assert editor.toPlainText() == "YabcX"

    def test_multiline_delete_reports_end_point(self, editor, qtbot):
        """Test deleting a selection across lines reports the right edit rows."""
        editor.setPlainText("a\nbb\ncc\nd")
        edits = []
        editor.document().byteContentsChange.connect(lambda *args: edits.append(args))
        cursor = editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(8, cursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        start_byte, old_end_byte, new_end_byte, start, old_end, new_end = edits[-1]
        assert (start_byte, old_end_byte, new_end_byte) == (4, 16, 4)
        assert (start.row, start.column) == (1, 0)
        assert (old_end.row, old_end.column) == (3, 0)
        assert (new_end.row, new_end.column) == (1, 0)

    def test_option_updates_reach_editor(self, bare_editor, qtbot):
        """Changing the options after the editor is shown changes how it edits"""
        simulate_keypress(qtbot, bare_editor, QtCore.Qt.Key.Key_Tab)
        assert bare_editor.toPlainText() == "    "
        bare_editor.options["indent_using_tabs"] = True
        simulate_keypress(qtbot, bare_editor, QtCore.Qt.Key.Key_Tab)
        assert bare_editor.toPlainText() == "    \t"

    def test_word_deletes(self, editor):
        editor.setPlainText("one two three")
        set_cursor_position(editor, 7)
        editor.delete(QtGui.QTextCursor.MoveOperation.PreviousWord)
        assert editor.toPlainText() == "one  three"
        editor.delete(QtGui.QTextCursor.MoveOperation.NextWord)
        assert editor.toPlainText() == "one three"
        assert_tree_matches_fresh_parse(editor)

    def test_colors_option(self, bare_editor):
        bare_editor.options["colors"] = {"bg": "#010203"}
        palette = bare_editor.palette()
        assert palette.color(QtGui.QPalette.ColorRole.Base) == QtGui.QColor("#010203")
        # Colors the theme doesn't set fall back to their defaults
        assert palette.color(QtGui.QPalette.ColorRole.Text) == gui_color({}, "fg")

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
        assert editor.toPlainText() == "Hello\n"

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
        """Clearing the document also clears the tree and the extra cursors"""
        editor.setPlainText("def foo():\n    pass")
        editor.cursors.replace_all([CursorState(0, 0), CursorState(5, 5)])
        editor.clear()
        assert editor.toPlainText() == ""
        assert editor.cursors.secondary == []
        assert_tree_matches_fresh_parse(editor)

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
        assert len(editor.cursors.secondary) == 2
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Escape)
        assert len(editor.cursors.secondary) == 0


KEY = QtCore.Qt.Key
MOD = QtCore.Qt.KeyboardModifier


class TestEditsOutsideTheKeyHandlers:
    """Every way of editing the text types at every cursor, and keeps the tree"""

    def two_cursors(self, editor):
        editor.setPlainText("a\nb")
        editor.cursors.replace_all([CursorState(1, 1), CursorState(3, 3)])

    def test_numpad_digit(self, editor, qtbot):
        self.two_cursors(editor)
        simulate_keypress(qtbot, editor, KEY.Key_1, "1", MOD.KeypadModifier)
        assert editor.toPlainText() == "a1\nb1"
        assert_tree_matches_fresh_parse(editor)

    def test_altgr_character(self, editor, qtbot):
        self.two_cursors(editor)
        altgr = MOD.ControlModifier | MOD.AltModifier
        simulate_keypress(qtbot, editor, KEY.Key_Q, "@", altgr)
        assert editor.toPlainText() == "a@\nb@"
        assert_tree_matches_fresh_parse(editor)

    def test_ctrl_letter_is_not_typed(self, editor, qtbot):
        editor.setPlainText("a")
        simulate_keypress(qtbot, editor, KEY.Key_Q, "\x11", MOD.ControlModifier)
        assert editor.toPlainText() == "a"

    def test_numpad_enter(self, editor, qtbot):
        self.two_cursors(editor)
        simulate_keypress(qtbot, editor, KEY.Key_Enter, "\r", MOD.KeypadModifier)
        assert editor.toPlainText() == "a\n\nb\n"
        assert_tree_matches_fresh_parse(editor)

    def test_insert_plain_text(self, editor):
        self.two_cursors(editor)
        editor.insertPlainText("x = 1")
        assert editor.toPlainText() == "ax = 1\nbx = 1"
        assert_tree_matches_fresh_parse(editor)

    def test_append_plain_text(self, editor):
        editor.setPlainText("x = 1")
        editor.appendPlainText("y = 2")
        assert editor.toPlainText() == "x = 1\ny = 2"
        assert_tree_matches_fresh_parse(editor)

    def test_context_menu_cuts_every_cursor(self, editor):
        editor.setPlainText("ab\nab")
        editor.cursors.replace_all([CursorState(0, 1), CursorState(3, 4)])
        menu = editor.create_context_menu()
        actions = {a.text(): a for a in menu.actions()}
        assert not actions["&Undo"].isEnabled()
        actions["Cu&t"].trigger()
        assert editor.toPlainText() == "b\nb"
        assert_tree_matches_fresh_parse(editor)

    def test_input_method_text_rebuilds_the_tree(self, editor):
        self.two_cursors(editor)
        # Qt types input method text with its own cursor, at the primary only
        event = QtGui.QInputMethodEvent()
        event.setCommitString("é")
        editor.inputMethodEvent(event)
        assert editor.toPlainText() == "aé\nb"
        assert editor.cursors.secondary == []
        assert_tree_matches_fresh_parse(editor)
