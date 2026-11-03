"""Tests for copying, cutting, pasting and dropping text"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui, QtWidgets

from QCodeSitter.cursors.state import CursorState
from tests.helpers import (
    assert_tree_matches_fresh_parse,
    get_cursor_positions,
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


@pytest.mark.usefixtures("clipboard")
class TestClipboardOperations:
    def test_paste_with_no_mime_data(self, editor, monkeypatch):
        # A clipboard that was never used has none on some platforms
        class EmptyClipboard:
            def mimeData(self):
                return None

        monkeypatch.setattr(QtWidgets.QApplication, "clipboard", EmptyClipboard)
        editor.setPlainText("Hello")
        editor.paste()
        assert editor.toPlainText() == "Hello"

    def test_copy_selection(self, editor, clipboard):
        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 0, 5)
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_C,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert clipboard.text() == "Hello"

    def test_cut_selection(self, editor, clipboard):
        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 0, 6)
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_X,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "World"
        assert clipboard.text() == "Hello "

    @pytest.mark.parametrize("cursors", [[0], [0, 2]])
    def test_copy_and_cut_without_selection_keep_clipboard(
        self, editor, clipboard, cursors
    ):
        clipboard.setText("keep")
        editor.setPlainText("abc")
        editor.cursors.replace_all([CursorState(pos, pos) for pos in cursors])
        for key in (QtCore.Qt.Key.Key_C, QtCore.Qt.Key.Key_X):
            simulate_keypress(
                editor, key, modifiers=QtCore.Qt.KeyboardModifier.ControlModifier
            )
        assert clipboard.text() == "keep"
        assert editor.toPlainText() == "abc"

    def test_paste_text(self, editor, clipboard):
        editor.setPlainText("")
        clipboard.setText("Pasted")
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_V,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "Pasted"

    def test_paste_replaces_selection(self, editor, clipboard):
        editor.setPlainText("Hello World")
        set_cursor_selection(editor, 6, 11)
        clipboard.setText("Python")
        simulate_keypress(
            editor,
            QtCore.Qt.Key.Key_V,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert editor.toPlainText() == "Hello Python"
