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
        self.shortcut_actions: list[QtWidgets.QAction] = []

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

    def getHotkeys(self) -> list[QtWidgets.QAction]:
        return []

    def hasKeyPress(self) -> bool:
        return False

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> bool:
        raise NotImplementedError("You must implement the keyPressEvent")