from __future__ import annotations

from Qt import QtCore, QtGui, QtWidgets
from tree_sitter import Point

from .constants import ENC


class TrackedDocument(QtGui.QTextDocument):
    """A subclass of QTextDocument that tracks UTF-16 code unit position changes
    Connect to the `byteContentsChange` signal to get those updates

    Note: Despite the signal name 'byteContentsChange', positions are now in UTF-16
    code units, which directly correspond to Qt's character positions. This makes
    integration with tree-sitter's UTF-16 mode seamless.
    """

    byteContentsChange = QtCore.Signal(int, int, int, Point, Point, Point)
    fullUpdateRequest = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lay = QtWidgets.QPlainTextDocumentLayout(self)
        self.setDocumentLayout(self.lay)

    def point_to_char(self, point: Point) -> int:
        """Get the document-global character offset from a tree-sitter Point

        Since tree-sitter now uses UTF-16 encoding, point.column is already
        in UTF-16 code units, which matches Qt's character positions exactly.
        """
        block = self.findBlockByNumber(point.row)
        return block.position() + point.column

    def point_to_byte(self, point: Point) -> int:
        """Get the document-global UTF-16 byte offset from a tree-sitter Point

        Args:
            point: Tree-sitter Point with row and column (column in code units)

        Returns:
            Byte offset in UTF-16LE encoding (for tree-sitter)
        """
        # Convert code unit position to byte offset (2 bytes per code unit)
        return self.point_to_char(point) * 2

    def byte_to_char(self, byteidx: int) -> int:
        """Convert UTF-16 byte offset to character index

        Args:
            byteidx: Byte offset in UTF-16LE encoding (from tree-sitter)

        Returns:
            Character index (code unit offset) for Qt
        """
        # Tree-sitter returns byte offsets. In UTF-16LE, each code unit is 2 bytes
        return byteidx // 2

    def manual_contents_change(self, position: int, removed: str, added: str):
        """Handle document content changes incrementally.

        Emits a byteContentsChange Signal containing this data:
            start byte index
            old end byte index
            new end byte index
            start Point
            old end Point
            new end Point

        Args:
            position: UTF-16 code unit position where change occurred
            removed: The text removed from the document if any
            added: The text added to the document if any
        """
        start_block = self.findBlock(position)
        start_line = start_block.blockNumber()
        start_col = (position - start_block.position()) * 2
        start_byte = position * 2

        def end_point(text: str) -> tuple[int, Point]:
            """Get the end byte and end point of text inserted at position"""
            # QTextCursor.selectedText uses the paragraph separator for newlines
            text = text.replace(" ", "\n")
            lines = text.count("\n")
            if lines == 0:
                col = start_col + len(text.encode(ENC))
            else:
                col = len(text[text.rfind("\n") + 1 :].encode(ENC))
            return start_byte + len(text.encode(ENC)), Point(start_line + lines, col)

        old_end_byte, old_end_point = end_point(removed)
        new_end_byte, new_end_point = end_point(added)
        self.byteContentsChange.emit(
            start_byte,
            old_end_byte,
            new_end_byte,
            Point(start_line, start_col),
            old_end_point,
            new_end_point,
        )
