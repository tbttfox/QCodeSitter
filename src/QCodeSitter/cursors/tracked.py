from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from Qt import QtGui

if TYPE_CHECKING:
    from ..tracked_document import TrackedDocument


class TrackedCursor(QtGui.QTextCursor):
    """A QTextCursor that reports its text edits to its TrackedDocument

    insertText, insertBlock, removeSelectedText, deleteChar and
    deletePreviousChar are reported, so the tree can follow them. The rich text
    inserts, like insertHtml, raise instead of editing behind the tree's back
    """

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

    def insertBlock(self, *args: Any, **kwargs: Any) -> None:
        position, removed = self._replaced_span()
        super().insertBlock(*args, **kwargs)
        self._doc.report_edit(position, removed, "\n")

    def insertText(
        self, text: str, format: QtGui.QTextCharFormat | None = None
    ) -> None:
        position, removed = self._replaced_span()
        if format is not None:
            super().insertText(text, format)
        else:
            super().insertText(text)
        self._doc.report_edit(position, removed, text)

    def _untracked(self, name: str) -> NoReturn:
        raise NotImplementedError(
            f"TrackedCursor.{name} would edit the document without updating "
            "the tree, use insertText"
        )

    def insertFragment(self, *args: object, **kwargs: object) -> NoReturn:
        self._untracked("insertFragment")

    def insertFrame(self, *args: object, **kwargs: object) -> NoReturn:
        self._untracked("insertFrame")

    def insertHtml(self, *args: object, **kwargs: object) -> NoReturn:
        self._untracked("insertHtml")

    def insertImage(self, *args: object, **kwargs: object) -> NoReturn:
        self._untracked("insertImage")

    def insertList(self, *args: object, **kwargs: object) -> NoReturn:
        self._untracked("insertList")

    def insertMarkdown(self, *args: object, **kwargs: object) -> NoReturn:
        self._untracked("insertMarkdown")

    def insertTable(self, *args: object, **kwargs: object) -> NoReturn:
        self._untracked("insertTable")

    def _replaced_span(self) -> tuple[int, str]:
        """Where an insert starts, and the selected text it replaces"""
        if self.hasSelection():
            return self.selectionStart(), self.selectedText()
        return self.position(), ""
