from __future__ import annotations
from typing import Generator

from Qt.QtWidgets import QPlainTextDocumentLayout
from Qt.QtCore import Signal, Slot
from Qt.QtGui import (
    QTextBlock,
    QTextDocument,
)
from tree_sitter import Point
from .constants import ENC


class TrackedDocument(QTextDocument):
    """A subclass of QTextDocument that tracks UTF-16 code unit position changes
    Connect to the `byteContentsChange` signal to get those updates

    Note: Despite the signal name 'byteContentsChange', positions are now in UTF-16
    code units, which directly correspond to Qt's character positions. This makes
    integration with tree-sitter's UTF-16 mode seamless.
    """

    byteContentsChange = Signal(int, int, int, Point, Point, Point)
    fullUpdateRequest = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lay = QPlainTextDocumentLayout(self)
        self.setDocumentLayout(self.lay)
        self._prev_line_count = 0
        self._prev_char_count = 0
        self.contentsChange.connect(self._on_contents_change)

    def point_to_char(self, point: Point) -> int:
        """Get the document-global character offset from a tree-sitter Point

        Since tree-sitter now uses UTF-16 encoding, point.column is already
        in UTF-16 code units, which matches Qt's character positions exactly.
        """
        block = self.findBlockByNumber(point.row)
        return block.position() + point.column

    def line_to_byte(self, line: int) -> int:
        """Get the document-global UTF-16 byte offset for the start of a line

        Returns:
            Byte offset in UTF-16LE encoding (for tree-sitter)
        """
        block = self.findBlockByNumber(line)
        # Convert code unit position to byte offset (2 bytes per code unit)
        return block.position() * 2

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

    def iter_line_range(
        self, start: int = 0, count: int = -1
    ) -> Generator[str, None, None]:
        """Iterate over a range of lines in the document, including any
        newline characters. If no range is given, do the whole document"""
        block: QTextBlock = (
            self.begin() if start == 0 else self.findBlockByNumber(start)
        )
        outputted = 0
        while block.isValid():
            text = block.text()
            nextblock = block.next()
            if nextblock.isValid():
                text += "\n"
            yield text
            outputted += 1

            if outputted == count:
                break
            block = nextblock

    @Slot(int, int, int)
    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        """Handle document content changes incrementally.

        Args:
            position: UTF-16 code unit position where change occurred
            chars_removed: Number of UTF-16 code units removed
            chars_added: Number of UTF-16 code units added
        """
        return
        # Note: Don't skip when document is empty after deletion - tree still needs update
        if self.isEmpty() and chars_added == 0:
            # Document is now empty and nothing was added, just signal empty tree
            return

        new_char_count = self.characterCount()
        new_line_count = self.blockCount()
        if self._prev_char_count - chars_removed + chars_added != new_char_count:
            # oops there's a tracking issue
            self._prev_char_count = new_char_count
            self._prev_line_count = new_line_count
            self.fullUpdateRequest.emit()
            return

        start_block = self.findBlock(position)
        start_line = start_block.blockNumber()
        new_end_line = self.findBlock(position + chars_added).blockNumber()
        old_end_line = new_end_line - new_line_count + self._prev_line_count

        next_block = start_block.next()
        if next_block.isValid():
            new_end_bytes = next_block.position() * 2
        else:
            new_end_bytes = new_char_count * 2

        byte_delta = 2 * (chars_removed - chars_added)

        self._prev_char_count = new_char_count
        self._prev_line_count = new_line_count
        self.byteContentsChange.emit(
            position * 2,
            new_end_bytes + byte_delta,
            new_end_bytes,
            Point(start_line, (position - start_block.position()) * 2),
            Point(old_end_line + 1, 0),
            Point(start_line + 1, 0),
        )

    def manual_contents_change(
        self, position: int, bytes_removed: bytes, bytes_added: bytes
    ):
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
            bytes_removed: The bytestring removed from the document if any
            bytes_added: The bytestring added to the document if any
        """
        start_block = self.findBlock(position)
        start_line = start_block.blockNumber()
        bytenewline = "\n".encode(ENC)

        lines_removed = bytes_removed.count(bytenewline)
        lines_added = bytes_added.count(bytenewline)

        pos_in_block = position - start_block.position()
        if lines_removed == 0:
            old_end_pib = (pos_in_block * 2) + len(bytes_removed)
        else:
            old_end_pib = len(bytes_removed.rsplit(bytenewline)[-1])

        if lines_added == 0:
            new_end_pib = (pos_in_block * 2) + len(bytes_added)
        else:
            new_end_pib = len(bytes_added.rsplit(bytenewline)[-1])

        self.byteContentsChange.emit(
            position * 2,
            position * 2 + len(bytes_removed),
            position * 2 + len(bytes_added),
            Point(start_line, pos_in_block * 2),
            Point(start_line + lines_removed, old_end_pib),
            Point(start_line + lines_added, new_end_pib),
        )
