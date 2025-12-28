from __future__ import annotations
from typing import Collection, TYPE_CHECKING
from Qt.QtGui import QKeyEvent, QResizeEvent

if TYPE_CHECKING:
    from QtShortcutManager import ShortcutSlotGroup
    from ..line_editor import CodeEditor
    from ..editor_options import EditorOptions


class Behavior:
    def __init__(self, editor: CodeEditor):
        self.editor: CodeEditor = editor
        self.options: EditorOptions = editor.options
        self.listen: set[str] = set()
        self.options.optionsUpdated.connect(self.updateOptions)

    def setListen(self, listen: set[str]):
        self.listen = listen

    def updateAll(self):
        self.updateOptions(self.listen)

    def updateOptions(self, keys: Collection[str]):
        carekeys = set(keys) & self.listen
        for key in carekeys:
            setattr(self, key, self.options[key])

    def remove(self):
        pass


class HasKeyPress:
    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        raise NotImplementedError("You must implement the keyPressEvent")


class HasResize:
    def resizeEvent(self, event: QResizeEvent) -> bool:
        raise NotImplementedError("You must implement the resizeEvent")


class HasHotkeys:
    """Interface for behaviors that provide user-configurable shortcuts.

    Use this interface for shortcuts that:
    - Use modifier keys (Ctrl, Alt, Shift) with commands
    - Should be user-configurable
    - Are context-independent or have broad applicability

    Do NOT use this for intrinsic editing behaviors like Tab, Return, Backspace, etc.
    """
    def getHotkeys(self) -> ShortcutSlotGroup:
        raise NotImplementedError("You must implement getHotkeys")
