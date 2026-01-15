from __future__ import annotations
from Qt import QtGui
from typing import TYPE_CHECKING, Optional
from .constants import ENC

if TYPE_CHECKING:
    from .line_tracker import TrackedDocument


class TrackedCursor(QtGui.QTextCursor):
    """A subclass of the QTextCursor that provides richer information about
    the changes it makes back to its document"""

    def __init__(self, document: TrackedDocument, cursor: QtGui.QTextCursor):
        self._doc = document
        super().__init__(cursor)

    def deleteChar(self):
        ttc = QtGui.QTextCursor(self)
        ttc.movePosition(ttc.MoveOperation.PreviousCharacter, ttc.MoveMode.KeepAnchor)
        bytes_removed = ttc.selectedText().encode(ENC)
        position = self.position()
        super().deleteChar()
        self._doc.manual_contents_change(position, bytes_removed, b"")

    def deletePreviousChar(self):
        ttc = QtGui.QTextCursor(self)
        ttc.movePosition(ttc.MoveOperation.NextCharacter, ttc.MoveMode.KeepAnchor)
        bytes_removed = ttc.selectedText().encode(ENC)
        position = ttc.position()
        super().deletePreviousChar()
        self._doc.manual_contents_change(position, bytes_removed, b"")

    def removeSelectedText(self):
        bytes_removed = self.selectedText().encode(ENC)
        position = self.selectionStart()
        super().removeSelectedText()
        self._doc.manual_contents_change(position, bytes_removed, b"")

    def insertBlock(self, *args, **kwargs):
        bytes_added = "\n".encode(ENC)
        position = self.position()
        super().insertBlock(*args, **kwargs)
        self._doc.manual_contents_change(position, b"", bytes_added)

    def insertText(self, text, format: Optional[QtGui.QTextCharFormat] = None):
        bytes_added = text.encode(ENC)
        if self.hasSelection():
            position = self.selectionStart()
            bytes_removed = self.selectedText().encode(ENC)
        else:
            position = self.position()
            bytes_removed = b""
        if format:
            super().insertText(text, format)
        else:
            super().insertText(text)
        self._doc.manual_contents_change(position, bytes_removed, bytes_added)
