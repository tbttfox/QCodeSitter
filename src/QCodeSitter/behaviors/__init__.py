from __future__ import annotations
from typing import Collection, TYPE_CHECKING
from Qt import QtGui

if TYPE_CHECKING:
    from QtShortcutManager import ShortcutSlotGroup
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
        self.updateOptions(self.listen)

    def updateOptions(self, keys: Collection[str]):
        carekeys = set(keys) & self.listen
        for key in carekeys:
            setattr(self, key, self.options[key])

    def remove(self):
        pass


class HasKeyPress:
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> bool:
        raise NotImplementedError("You must implement the keyPressEvent")


class HasResize:
    def resizeEvent(self, event: QtGui.QResizeEvent) -> bool:
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


class HasPaint:
    """Interface for behaviors that need to customize paint events.

    Use this interface for behaviors that need to draw custom content
    in the editor viewport (e.g., overlays, backgrounds, decorations).

    The painter is provided by the editor and is already active on the viewport.
    """

    def paintEvent(self, event: QtGui.QPaintEvent, painter) -> bool:
        raise NotImplementedError("You must implement the paintEvent")


class HasUndoRedo:
    """Interface for behaviors that need to be notified about undo/redo operations.

    Use this interface for behaviors that need to prepare before undo/redo
    or update after undo/redo completes (e.g., syntax highlighting that needs
    to sync with document state).
    """

    def prepareUndo(self):
        """Called before undo operation - prepare for document change"""
        pass

    def prepareRedo(self):
        """Called before redo operation - prepare for document change"""
        pass

    def afterUndoRedo(self):
        """Called after undo/redo completes - update to match new document state"""
        pass
