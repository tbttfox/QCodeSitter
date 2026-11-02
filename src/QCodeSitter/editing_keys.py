"""The editor's built-in keys: typing, deleting, moving, and the edit commands"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .utils import KEY, MO, MOD

if TYPE_CHECKING:
    from Qt import QtGui

    from .code_editor import CodeEditor

# Delete key -> (move operation, move operation with Ctrl held)
_DELETE_OPS: dict[KEY, tuple[MO, MO]] = {
    KEY.Key_Backspace: (MO.PreviousCharacter, MO.PreviousWord),
    KEY.Key_Delete: (MO.NextCharacter, MO.NextWord),
}

# Movement key -> (move operation, move operation with Ctrl held)
# None is smart home, which toggles between the indent and column 0
_MOVE_OPS: dict[KEY, tuple[MO | None, MO]] = {
    KEY.Key_Left: (MO.Left, MO.WordLeft),
    KEY.Key_Right: (MO.Right, MO.WordRight),
    KEY.Key_Up: (MO.Up, MO.Up),
    KEY.Key_Down: (MO.Down, MO.Down),
    KEY.Key_Home: (None, MO.Start),
    KEY.Key_End: (MO.EndOfLine, MO.End),
}

# The modifiers that can be held while typing text, besides Shift: the
# numpad, and AltGr, which is Ctrl+Alt on Windows and Group Switch elsewhere
_TEXT_MODIFIERS = MOD.ShiftModifier | MOD.KeypadModifier | MOD.GroupSwitchModifier
_ALTGR = MOD.ControlModifier | MOD.AltModifier


class EditingKeys:
    """Applies the built-in editing keys to every cursor of an editor

    The editor gives a key to its behaviors first, and to this after them
    """

    def __init__(self, editor: CodeEditor) -> None:
        self.editor = editor
        # Whether the next word character joins the last one's undo step
        self._can_join = False
        # (modifier, action) pairs for the keys that run editor commands
        self._command_keys: dict[KEY, tuple[tuple[MOD, Callable[[], None]], ...]] = {
            KEY.Key_C: ((MOD.ControlModifier, editor.copy),),
            KEY.Key_Insert: (
                (MOD.ControlModifier, editor.copy),
                (MOD.ShiftModifier, editor.paste),
            ),
            KEY.Key_V: ((MOD.ControlModifier, editor.paste),),
            KEY.Key_X: ((MOD.ControlModifier, editor.cut),),
            KEY.Key_Z: ((MOD.ControlModifier, editor.undo),),
            KEY.Key_Y: ((MOD.ControlModifier, editor.redo),),
        }

    def end_undo_step(self) -> None:
        """Make the next typing start a new undo step"""
        self._can_join = False

    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        """Apply an editing key to all the cursors

        Returns whether the key was handled
        """
        key = event.key()
        modifiers = event.modifiers()
        cursors = self.editor.cursors

        if key == KEY.Key_Escape:
            cursors.clear_secondary()
            return True

        if self._type_text(event):
            return True

        if modifiers == MOD.ControlModifier and key == KEY.Key_A:
            cursors.clear_secondary()
            return False

        delete_ops = _DELETE_OPS.get(key)
        if delete_ops is not None:
            self.editor.delete(delete_ops[bool(modifiers & MOD.ControlModifier)])
            return True

        # Alt+arrow combinations are hotkeys, like Ctrl+Alt+Up to add a cursor
        if modifiers & MOD.AltModifier:
            return False

        move_ops = _MOVE_OPS.get(key)
        if move_ops is None:
            return self._run_command_key(event)
        select = bool(modifiers & MOD.ShiftModifier)
        move_op = move_ops[bool(modifiers & MOD.ControlModifier)]
        if move_op is None:
            cursors.smart_home(select)
        else:
            cursors.move(move_op, select)
        return True

    def _type_text(self, event: QtGui.QKeyEvent) -> bool:
        """Insert the text of a typing key at every cursor

        Returns whether the key typed text
        """
        text = event.text()
        typing = (
            text
            and text.isprintable()
            and event.modifiers() & ~_TEXT_MODIFIERS in (MOD.NoModifier, _ALTGR)
        )
        if not typing:
            self._can_join = False
            return False
        # Typing a word is a single undo step, so each character joins the last
        is_word = text.isalnum() or text == "_"
        self.editor.insert_text(text, join_edit=self._can_join and is_word)
        self._can_join = is_word
        return True

    def _run_command_key(self, event: QtGui.QKeyEvent) -> bool:
        """Run the editor command for Tab, Enter, or a clipboard/undo shortcut"""
        key = event.key()
        options = self.editor.options
        if key == KEY.Key_Tab:
            if options["indent_using_tabs"]:
                self.editor.insert_text("\t")
            else:
                self.editor.insert_text(" " * options["space_indent_width"])
            return True
        # Key_Enter is the numpad
        if key in (KEY.Key_Return, KEY.Key_Enter):
            self.editor.insert_text("\n")
            return True
        for modifier, command in self._command_keys.get(key, ()):
            if event.modifiers() & modifier:
                command()
                return True
        return False
