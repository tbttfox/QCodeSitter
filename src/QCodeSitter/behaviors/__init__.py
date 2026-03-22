from __future__ import annotations
from typing import Collection, TYPE_CHECKING
from Qt import QtGui, QtWidgets

if TYPE_CHECKING:
    from ..code_editor import CodeEditor
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
        if self.editor._loaded:
            self.updateOptions(self.listen)

    def updateOptions(self, keys: Collection[str]):
        carekeys = set(keys) & self.listen
        for key in carekeys:
            setattr(self, key, self.options[key])

    def remove(self):
        pass


class HasKeyPress:
    """Marker for behaviors that handle key press events with short-circuit semantics.

    Implement keyPressEvent and return True to consume the event and stop
    further dispatch. addBehavior registers this behavior for direct dispatch
    via CodeEditor._keypressBehaviors.
    """

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> bool:
        raise NotImplementedError("You must implement the keyPressEvent")


class HasHotkeys:
    """Interface for behaviors that provide keyboard shortcuts.

    Use this interface for shortcuts that:
    - Use modifier keys (Ctrl, Alt, Shift) with commands
    - Are context-independent or have broad applicability

    Do NOT use this for intrinsic editing behaviors like Tab, Return, Backspace, etc.
    """

    _shortcut_actions: list[QtWidgets.QAction] = []

    def getHotkeys(self) -> list[QtWidgets.QAction]:
        raise NotImplementedError("You must implement getHotkeys")


