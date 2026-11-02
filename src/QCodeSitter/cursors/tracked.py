from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtGui

if TYPE_CHECKING:
    from ..tracked_document import TrackedDocument


class TrackedCursor(QtGui.QTextCursor):
    """A subclass of the QTextCursor that provides richer information about
    the changes it makes back to its document"""

    def __init__(self, document: TrackedDocument, cursor: QtGui.QTextCursor) -> None:
        self._doc = document
        super().__init__(cursor)

    def deleteChar(self) -> None:
        if self.hasSelection():
            self.removeSelectedText()
            return
        ttc = QtGui.QTextCursor(self)
        ttc.movePosition(ttc.MoveOperation.NextCharacter, ttc.MoveMode.KeepAnchor)
        removed = ttc.selectedText()
        position = self.position()
        super().deleteChar()
        self._doc.report_edit(position, removed, "")

    def deletePreviousChar(self) -> None:
        if self.hasSelection():
            self.removeSelectedText()
            return
        ttc = QtGui.QTextCursor(self)
        ttc.movePosition(ttc.MoveOperation.PreviousCharacter, ttc.MoveMode.KeepAnchor)
        removed = ttc.selectedText()
        position = ttc.position()
        super().deletePreviousChar()
        self._doc.report_edit(position, removed, "")

    def removeSelectedText(self) -> None:
        removed = self.selectedText()
        position = self.selectionStart()
        super().removeSelectedText()
        self._doc.report_edit(position, removed, "")

    def insertBlock(self, *args, **kwargs) -> None:
        position, removed = self._replaced_span()
        super().insertBlock(*args, **kwargs)
        self._doc.report_edit(position, removed, "\n")

    def insertText(self, text, format: QtGui.QTextCharFormat | None = None) -> None:
        position, removed = self._replaced_span()
        if format is not None:
            super().insertText(text, format)
        else:
            super().insertText(text)
        self._doc.report_edit(position, removed, text)

    def _replaced_span(self) -> tuple[int, str]:
        """Where an insert starts, and the selected text it replaces"""
        if self.hasSelection():
            return self.selectionStart(), self.selectedText()
        return self.position(), ""
