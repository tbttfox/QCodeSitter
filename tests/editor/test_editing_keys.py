"""Tests for the editor's built-in keys, without any behaviors"""

from __future__ import annotations

from Qt import QtCore, QtGui

from QCodeSitter.cursors.state import CursorState
from QCodeSitter.editing_keys import EditingKeys
from tests.helpers import get_cursor_positions

KEY = QtCore.Qt.Key
MOD = QtCore.Qt.KeyboardModifier


def key_event(key, text: str = "", modifiers=MOD.NoModifier) -> QtGui.QKeyEvent:
    return QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key, modifiers, text)


class TestEditingKeys:
    def test_keys_for_qt_are_passed_on(self, bare_editor):
        keys: EditingKeys = bare_editor.keys
        bare_editor.setPlainText("ab\ncd")
        bare_editor.cursors.replace_all([CursorState(0, 0), CursorState(3, 3)])
        # Ctrl+Alt+Up is a hotkey, and Ctrl+A is Qt's select all
        assert not keys.handle_key_press(
            key_event(KEY.Key_Up, modifiers=MOD.ControlModifier | MOD.AltModifier)
        )
        assert not keys.handle_key_press(
            key_event(KEY.Key_A, modifiers=MOD.ControlModifier)
        )
        # Selecting everything leaves one cursor
        assert bare_editor.cursors.secondary == []

    def test_moves_every_cursor(self, bare_editor):
        bare_editor.setPlainText("ab\ncd")
        bare_editor.cursors.replace_all([CursorState(0, 0), CursorState(3, 3)])
        assert bare_editor.keys.handle_key_press(key_event(KEY.Key_End))
        assert get_cursor_positions(bare_editor) == [2, 5]
        assert bare_editor.keys.handle_key_press(key_event(KEY.Key_Home))
        assert get_cursor_positions(bare_editor) == [0, 3]

    def test_a_typed_word_is_one_undo_step(self, bare_editor):
        keys: EditingKeys = bare_editor.keys
        for char in "ab":
            keys.handle_key_press(key_event(KEY.Key_A, char))
        keys.end_undo_step()
        keys.handle_key_press(key_event(KEY.Key_C, "c"))
        assert bare_editor.toPlainText() == "abc"
        bare_editor.document().undo()
        assert bare_editor.toPlainText() == "ab"
        bare_editor.document().undo()
        assert bare_editor.toPlainText() == ""

    def test_command_keys(self, bare_editor):
        keys: EditingKeys = bare_editor.keys
        keys.handle_key_press(key_event(KEY.Key_Tab))
        assert bare_editor.toPlainText() == "    "
        bare_editor.options["indent_using_tabs"] = True
        keys.handle_key_press(key_event(KEY.Key_Tab))
        assert bare_editor.toPlainText() == "    \t"
        assert keys.handle_key_press(
            key_event(KEY.Key_Z, modifiers=MOD.ControlModifier)
        )
        assert bare_editor.toPlainText() == "    "
        # An unused Ctrl combination is left to Qt
        assert not keys.handle_key_press(
            key_event(KEY.Key_F, modifiers=MOD.ControlModifier)
        )
