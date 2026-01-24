"""
Helper functions for QCodeSitter tests.
"""

from __future__ import annotations

from Qt import QtGui, QtCore

from QCodeSitter.code_editor import CodeEditor


def get_cursor_positions(editor: CodeEditor) -> list[int]:
    """Get all cursor positions (primary + secondary) sorted."""
    cursors, _ = editor.get_all_cursors()
    return [c.position for c in cursors]


def set_cursor_position(editor: CodeEditor, position: int):
    """Set the primary cursor position."""
    cursor = editor.textCursor()
    cursor.setPosition(position)
    editor.setTextCursor(cursor)


def set_cursor_selection(editor: CodeEditor, anchor: int, position: int):
    """Set the primary cursor with a selection."""
    cursor = editor.textCursor()
    cursor.setPosition(anchor)
    cursor.setPosition(position, QtGui.QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def simulate_keypress(
    qtbot,
    editor: CodeEditor,
    key: QtCore.Qt.Key,
    text: str = "",
    modifiers: QtCore.Qt.KeyboardModifier = QtCore.Qt.KeyboardModifier.NoModifier,
):
    """Simulate a key press event on the editor."""
    event = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyPress,
        key,
        modifiers,
        text,
    )
    editor.keyPressEvent(event)


def simulate_text_input(qtbot, editor: CodeEditor, text: str):
    """Simulate typing text into the editor."""
    for char in text:
        key = getattr(QtCore.Qt.Key, f"Key_{char.upper()}", QtCore.Qt.Key.Key_unknown)
        simulate_keypress(qtbot, editor, key, char)
