from __future__ import annotations
from typing import Collection, TYPE_CHECKING
from Qt.QtGui import QKeyEvent, QResizeEvent

if TYPE_CHECKING:
    from ..line_editor import CodeEditor
    from ..editor_options import EditorOptions


class Behavior:
    def __init__(self, editor: CodeEditor, listen: set[str]):
        self.editor: CodeEditor = editor
        self.options: EditorOptions = editor.options
        self.listen: set[str] = listen
        self.options.optionsUpdated.connect(self.updateOptions)
        self.updateOptions(self.listen)

    def updateOptions(self, keys: Collection[str]):
        carekeys = set(keys) & self.listen
        for key in carekeys:
            setattr(self, key, self.options[key])


class HasKeyPress:
    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        raise NotImplementedError("You must implement the keyPressEvent")


class HasResize:
    def resizeEvent(self, event: QResizeEvent) -> bool:
        raise NotImplementedError("You must implement the resizeEvent")
