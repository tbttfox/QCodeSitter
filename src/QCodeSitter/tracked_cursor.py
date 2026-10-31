from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtGui

if TYPE_CHECKING:
    from .line_tracker import TrackedDocument


class TrackedCursor(QtGui.QTextCursor):
    """A subclass of the QTextCursor that provides richer information about
    the changes it makes back to its document"""

    def __init__(self, document: TrackedDocument, cursor: QtGui.QTextCursor):
        self._doc = document
        super().__init__(cursor)

    def deleteChar(self):
        if self.hasSelection():
            return self.removeSelectedText()
        ttc = QtGui.QTextCursor(self)
        ttc.movePosition(ttc.MoveOperation.NextCharacter, ttc.MoveMode.KeepAnchor)
        removed = ttc.selectedText()
        position = self.position()
        super().deleteChar()
        self._doc.manual_contents_change(position, removed, "")

    def deletePreviousChar(self):
        if self.hasSelection():
            return self.removeSelectedText()
        ttc = QtGui.QTextCursor(self)
        ttc.movePosition(ttc.MoveOperation.PreviousCharacter, ttc.MoveMode.KeepAnchor)
        removed = ttc.selectedText()
        position = ttc.position()
        super().deletePreviousChar()
        self._doc.manual_contents_change(position, removed, "")

    def removeSelectedText(self):
        removed = self.selectedText()
        position = self.selectionStart()
        super().removeSelectedText()
        self._doc.manual_contents_change(position, removed, "")

    def insertBlock(self, *args, **kwargs):
        position = self.position()
        super().insertBlock(*args, **kwargs)
        self._doc.manual_contents_change(position, "", "\n")

    def insertText(self, text, format: QtGui.QTextCharFormat | None = None):
        if self.hasSelection():
            position = self.selectionStart()
            removed = self.selectedText()
        else:
            position = self.position()
            removed = ""
        if format:
            super().insertText(text, format)
        else:
            super().insertText(text)
        self._doc.manual_contents_change(position, removed, text)
