from typing import Generator

from Qt.QtWidgets import QPlainTextDocumentLayout
from Qt.QtCore import Signal, Slot
from Qt.QtGui import (
    QTextBlock,
    QTextDocument,
)
from tree_sitter import Point


class TrackedDocument(QTextDocument):
    """A subclass of QTextDocument that tracks UTF-16 code unit position changes
    Connect to the `byteContentsChange` signal to get those updates

    Note: Despite the signal name 'byteContentsChange', positions are now in UTF-16
    code units, which directly correspond to Qt's character positions. This makes
    integration with tree-sitter's UTF-16 mode seamless.
    """

    byteContentsChange = Signal(int, int, int, Point, Point, Point)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lay = QPlainTextDocumentLayout(self)
        self.setDocumentLayout(self.lay)
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

    def _get_line_length_utf16(self, block: QTextBlock) -> int:
        """Get the length of a line in UTF-16 code units, including newline if present"""
        length = len(block.text())
        if block.next().isValid():
            length += 1  # Add 1 for newline
        return length

    def _single_char_change(
        self, position: int, chars_added: int, chars_removed: int
    ) -> tuple[int, int, int, Point, Point, Point]:
        """Handle a single character change in UTF-16 code units

        With UTF-16 encoding, position values directly correspond to code units.
        Qt's position values already count surrogate pairs as 2 units, matching UTF-16.
        """
        start_block = self.findBlock(position)
        start_line = start_block.blockNumber()
        linebytes = (position - start_block.position()) * 2

        bytes_added = chars_added * 2
        bytes_removed = chars_removed * 2
        start_bytes = position * 2

        start_point = Point(start_line, linebytes)

        if chars_removed == 0:
            # Character added
            old_end_bytes = start_bytes
            old_end_point = start_point
            new_end_bytes = start_bytes + bytes_added

            # Check if we added a newline
            new_end_block = self.findBlock(position + chars_added)
            if new_end_block.blockNumber() > start_line:
                # Newline was added
                new_end_point = Point(start_line + 1, 0)
            else:
                # Regular character
                new_end_point = Point(start_line, linebytes + bytes_added)
        else:
            # Character removed
            new_end_bytes = start_bytes
            new_end_point = start_point
            old_end_bytes = start_bytes + bytes_removed

            # Assume we knew the character that was removed
            # If line count decreased, a newline was removed
            new_line_count = self.blockCount()
            if new_line_count < self.blockCount():
                # Newline was removed
                old_end_point = Point(start_line + 1, 0)
            else:
                # Regular character
                old_end_point = Point(start_line, linebytes + bytes_added)

        return (
            start_bytes,
            old_end_bytes,
            new_end_bytes,
            start_point,
            old_end_point,
            new_end_point,
        )

    def _multi_char_change(
        self, position: int, chars_added: int, chars_removed: int
    ) -> tuple[int, int, int, Point, Point, Point]:
        """Handle a multiple character change in UTF-16 code units

        For multi-character changes, we can still provide accurate positions
        since Qt's position values are already in UTF-16 code units.
        """
        start_block = self.findBlock(position)
        start_line = start_block.blockNumber()
        linebytes = (position - start_block.position()) * 2

        bytes_added = chars_added * 2
        bytes_removed = chars_removed * 2
        start_point = Point(start_line, linebytes)

        start_bytes = (position) * 2
        old_end_bytes = start_bytes + bytes_removed
        new_end_bytes = start_bytes + bytes_added

        # Calculate old end point (before the change)
        # We need to figure out where the old text ended
        if chars_removed > 0:
            # Estimate old end position by looking at current position
            # and the amount removed
            old_end_point = Point(start_line, linebytes + bytes_removed)
            # This is approximate - if newlines were removed, this won't be exact
            # but tree-sitter can handle approximate old positions
        else:
            old_end_point = Point(start_line, linebytes)

        # Calculate new end point (after the change)
        if chars_added > 0:
            new_end_block = self.findBlock(position + bytes_added)
            new_end_line = new_end_block.blockNumber()
            new_end_col = (start_bytes + bytes_added) - (new_end_block.position() * 2)
            new_end_point = Point(new_end_line, new_end_col)
        else:
            new_end_point = Point(start_line, linebytes)

        return (
            start_bytes,
            old_end_bytes,
            new_end_bytes,
            start_point,
            old_end_point,
            new_end_point,
        )

    @Slot(int, int, int)
    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        """Handle document content changes incrementally.

        Args:
            position: UTF-16 code unit position where change occurred
            chars_removed: Number of UTF-16 code units removed
            chars_added: Number of UTF-16 code units added
        """
        # Note: Don't skip when document is empty after deletion - tree still needs update
        if self.isEmpty() and chars_added == 0:
            # Document is now empty and nothing was added, just signal empty tree
            return

        # Short-circuit if just doing normal typing and backspacing
        if chars_removed | chars_added == 1 and chars_removed & chars_added == 0:
            ret = self._single_char_change(position, chars_added, chars_removed)
        else:
            ret = self._multi_char_change(position, chars_added, chars_removed)
        self.byteContentsChange.emit(*ret)
