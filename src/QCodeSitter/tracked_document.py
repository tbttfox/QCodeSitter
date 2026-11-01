from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore, QtGui, QtWidgets
from tree_sitter import Point

from .constants import ENC

if TYPE_CHECKING:
    from tree_sitter import Node


class TrackedDocument(QtGui.QTextDocument):
    """A QTextDocument that reports its edits in the form tree-sitter expects

    Qt positions are UTF-16 code units. Tree-sitter parses the document as
    UTF-16LE, so its offsets and Point columns are in bytes, which is always
    2 bytes per code unit. Every edit made through a TrackedCursor emits
    `byteContentsChange` with those byte offsets.
    """

    byteContentsChange = QtCore.Signal(int, int, int, Point, Point, Point)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setDocumentLayout(QtWidgets.QPlainTextDocumentLayout(self))

    @staticmethod
    def byte_to_char(byte_offset: int) -> int:
        """Convert a UTF-16LE byte offset from tree-sitter to a Qt position"""
        return byte_offset // 2

    @staticmethod
    def char_to_byte(position: int) -> int:
        """Convert a Qt position to a UTF-16LE byte offset for tree-sitter"""
        return position * 2

    def row_col_to_char(self, row: int, col: int) -> int:
        """Get the Qt position of a block row and a column in UTF-16 code units"""
        return self.findBlockByNumber(row).position() + col

    def node_text(self, node: Node) -> str:
        """Get the current text of a tree-sitter node of this document"""
        start, end = node.start_point, node.end_point
        lines = []
        block = self.findBlockByNumber(start.row)
        for row in range(start.row, end.row + 1):
            if not block.isValid():
                break
            data = block.text().encode(ENC)
            first = start.column if row == start.row else 0
            last = end.column if row == end.row else len(data)
            lines.append(data[first:last].decode(ENC, errors="replace"))
            block = block.next()
        return "\n".join(lines)

    def report_edit(self, position: int, removed: str, added: str) -> None:
        """Emit `byteContentsChange` for an edit at a Qt position

        The signal carries the start, old end and new end as UTF-16LE byte
        offsets, then the same three as Points with byte columns.
        """
        start_block = self.findBlock(position)
        start_line = start_block.blockNumber()
        start_col = self.char_to_byte(position - start_block.position())
        start_byte = self.char_to_byte(position)

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
