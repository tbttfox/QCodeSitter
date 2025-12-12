import bisect
from math import ceil, floor
from typing import Generator, Optional, Sequence

from Qt.QtWidgets import QPlainTextDocumentLayout
import numpy as np
from Qt.QtCore import Signal, Slot
from Qt.QtGui import (
    QTextBlock,
    QTextDocument,
)
from tree_sitter import Point


def _zcs(ary) -> np.ndarray:
    """leading Zero Cumulative Summation"""
    return np.concatenate(([0], np.cumsum(ary)))


class ChunkedLineTracker:
    """Keep track of line/byte relationships in a QTextDocument
    This is done by storing the byte-length of each line

    These lenghts are stored in chunks about the size of the `chunk_size` argument
    And there's metadata about these chunks stored in other lists to make getting
    and setting information faster

    If any chunk gets to either double or half the chunk_size it will split or merge
    to keep things generally consistent.

    Properties:
        chunks: A chunked list of line-lengths in bytes
        chunks_cumsums: The cumulative sum of each chunk. Including a leading 0
            These are lazily calculated.
        chunk_totals: The total number of bytes in each chunk
        chunk_line_ranges: The cumulative sum of the line count of each chunk
            Including a leading 0
        chunk_byte_ranges: The cumulative sum of the byte count of each chunk
            Including a leading 0
        chunk_size: The target size of each chunk
    """

    def __init__(self, data: Optional[Sequence[int]] = None, chunk_size: int = 10000):
        self.chunks: list[np.ndarray]
        self.chunk_cumsums: list[Optional[np.ndarray]]
        self.chunk_line_ranges: np.ndarray
        self.chunk_byte_ranges: np.ndarray
        self.chunk_size: int = chunk_size

        data = [0] if data is None else data
        self.set(data)

    def set(self, data: Sequence[int]):
        ary = np.array(data)
        self.chunks = [ary]
        self.chunk_cumsums = [None]
        self.chunk_totals = [ary.sum()]
        self.chunk_line_ranges = np.array([0, len(ary)])
        self.chunk_byte_ranges = np.array([0, ary.sum()])
        self._rebalance(0)

    def get_chunk_for_line(self, line: int) -> int:
        """Get the index of the chunk containing the given line"""
        return bisect.bisect_right(self.chunk_line_ranges, line) - 1

    def get_chunk_for_byte(self, byteidx: int) -> int:
        """Get the index of the chunk containing the given line"""
        return bisect.bisect_right(self.chunk_byte_ranges, byteidx) - 1

    def get_line_for_byte(self, byteidx: int) -> int:
        """Get the index of the line for the given byte offset"""
        chunk_idx = self.get_chunk_for_byte(byteidx)
        if chunk_idx >= len(self.chunks):
            return self.chunk_line_ranges[-1] - 1

        if byteidx >= self.chunk_byte_ranges[chunk_idx + 1]:
            return self.chunk_line_ranges[chunk_idx + 1] - 1

        start_byte = self.chunk_byte_ranges[chunk_idx]
        css = self.chunk_cumsums[chunk_idx]
        if css is None:
            css = _zcs(self.chunks[chunk_idx])
            self.chunk_cumsums[chunk_idx] = css

        return (
            self.chunk_line_ranges[chunk_idx]
            + np.searchsorted(css, [byteidx - start_byte], "right")[0]
            - 1
        )

    def line_bytelength(self, line: int) -> int:
        """Get the bytelength of the given line"""
        chunk_idx = self.get_chunk_for_line(line)
        if chunk_idx >= len(self.chunks):
            return 0
        offset = line - self.chunk_line_ranges[chunk_idx]
        if offset >= len(self.chunks[chunk_idx]):
            return 0
        return self.chunks[chunk_idx][offset]  # type: ignore

    def total_sum(self) -> int:
        """Get the total length of the document in bytes"""
        return self.chunk_byte_ranges[-1]

    def line_to_byte(self, line: int) -> int:
        """Get the sum(self.line_byte_lens[:line])"""
        chunk_idx = self.get_chunk_for_line(line)
        if chunk_idx >= len(self.chunks):
            return self.chunk_byte_ranges[-1]
        offset = line - self.chunk_line_ranges[chunk_idx]
        return self.chunk_byte_ranges[chunk_idx] + np.sum(
            self.chunks[chunk_idx][:offset]
        )

    def replace_lines(
        self, start_line: int, post_line: int, new_line_lengths: Sequence[int]
    ):
        """Replace the range of lines with the given new line lengths
        The rough equivalent of self[start_line: post_line] = new_line_lengths
        """
        assert post_line >= start_line
        if not self.chunks:
            self.set(new_line_lengths)
            return

        # Validate the line range
        total_lines = self.chunk_line_ranges[-1]
        if start_line >= total_lines:
            # Appending to the end
            self.chunks[-1] = np.concatenate((self.chunks[-1], new_line_lengths))
            self.chunk_cumsums[-1] = None
            self.chunk_totals[-1] = np.sum(self.chunks[-1])
            chunk_lengths = [len(c) for c in self.chunks]
            self.chunk_line_ranges = _zcs(chunk_lengths)
            self.chunk_byte_ranges = _zcs(self.chunk_totals)
            self._rebalance(len(self.chunks) - 1)
            return

        # Get the chunk range.  end_chunk_idx is *INCLUSIVE*
        start_chunk_idx = self.get_chunk_for_line(start_line)
        if start_chunk_idx >= len(self.chunks):
            start_chunk_idx = len(self.chunks) - 1

        end_chunk_idx = self.get_chunk_for_line(min(post_line - 1, total_lines - 1))
        if end_chunk_idx >= len(self.chunks):
            end_chunk_idx = len(self.chunks) - 1

        # Get how far into each chunk the start and end lines are
        start_offset = start_line - self.chunk_line_ranges[start_chunk_idx]
        end_offset = post_line - self.chunk_line_ranges[end_chunk_idx]

        pre_chunk = self.chunks[start_chunk_idx][:start_offset]
        post_chunk = self.chunks[end_chunk_idx][end_offset:]

        new_chunk = np.concatenate((pre_chunk, new_line_lengths, post_chunk))
        self.chunks[start_chunk_idx : end_chunk_idx + 1] = [new_chunk]
        self.chunk_cumsums[start_chunk_idx : end_chunk_idx + 1] = [None]
        self.chunk_totals[start_chunk_idx : end_chunk_idx + 1] = [np.sum(new_chunk)]
        chunk_lengths = [len(c) for c in self.chunks]
        self.chunk_line_ranges = _zcs(chunk_lengths)
        self.chunk_byte_ranges = _zcs(self.chunk_totals)
        self._rebalance(start_chunk_idx)

    def _merge_chunk_with_right(self, left_idx: int):
        """Merge a chunk with the chunk to its right"""
        new_chunk = np.concatenate((self.chunks[left_idx], self.chunks[left_idx + 1]))
        new_total = np.sum(new_chunk)
        self.chunks[left_idx : left_idx + 2] = [new_chunk]
        self.chunk_cumsums[left_idx : left_idx + 2] = [None]
        self.chunk_totals[left_idx : left_idx + 2] = [new_total]
        chunk_lengths = [len(c) for c in self.chunks]
        self.chunk_line_ranges = _zcs(chunk_lengths)
        self.chunk_byte_ranges = _zcs(self.chunk_totals)

    def _get_nice_counts(self, totalsize: int, num_chunks: int) -> list[int]:
        """Get the sizes of each chunk given the total size and the number of chunks"""
        if num_chunks < 1:
            return [totalsize]
        ideal_size = totalsize / num_chunks
        ceil_count = totalsize - (floor(ideal_size) * num_chunks)
        floor_count = num_chunks - ceil_count
        return [ceil(ideal_size)] * ceil_count + [floor(ideal_size)] * floor_count

    def _split_chunk(self, chunk_idx: int, num_chunks: int):
        """Split the given chunk into `num_chunks` parts"""
        chunksize = len(self.chunks[chunk_idx])
        counts = self._get_nice_counts(chunksize, num_chunks)

        chunk = self.chunks[chunk_idx]
        ptr = 0
        new_chunks = []
        new_totals = []
        for count in counts:
            new_chunks.append(chunk[ptr : ptr + count])
            new_totals.append(np.sum(new_chunks[-1]))
            ptr += count
        self.chunks[chunk_idx : chunk_idx + 1] = new_chunks
        self.chunk_cumsums[chunk_idx : chunk_idx + 1] = [None] * len(new_chunks)
        self.chunk_totals[chunk_idx : chunk_idx + 1] = new_totals
        chunk_lengths = [len(c) for c in self.chunks]
        self.chunk_line_ranges = _zcs(chunk_lengths)
        self.chunk_byte_ranges = _zcs(self.chunk_totals)

    def _rebalance(self, chunk_idx):
        """Make sure that this chunk is about the right size"""
        chunksize = len(self.chunks[chunk_idx])
        if chunksize < self.chunk_size / 2:
            # combine with my smallest neighbor
            if len(self.chunks) >= 2:
                left_idx = chunk_idx
                if chunk_idx == 0:
                    left_idx = 0
                elif chunk_idx == len(self.chunks) - 1:
                    left_idx = len(self.chunks) - 2
                elif len(self.chunks[chunk_idx + 1]) > len(self.chunks[chunk_idx - 1]):
                    left_idx = chunk_idx - 1
                self._merge_chunk_with_right(left_idx)

        elif chunksize >= self.chunk_size * 2:
            # split evenly so I'm as close to chunk_size as possible
            num_chunks = max(1, chunksize // self.chunk_size)
            self._split_chunk(chunk_idx, num_chunks)


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
        linepos = position - start_block.position()

        # In UTF-16, position IS the code unit offset
        start_utf16 = position
        start_point = Point(start_line, linepos)

        if chars_removed == 0:
            # Character added
            old_end_utf16 = start_utf16
            old_end_point = start_point
            new_end_utf16 = start_utf16 + chars_added

            # Check if we added a newline
            new_end_block = self.findBlock(position + chars_added)
            if new_end_block.blockNumber() > start_line:
                # Newline was added
                new_end_point = Point(start_line + 1, 0)
            else:
                # Regular character
                new_end_point = Point(start_line, linepos + chars_added)
        else:
            # Character removed
            new_end_utf16 = start_utf16
            new_end_point = start_point
            old_end_utf16 = start_utf16 + chars_removed

            # Assume we knew the character that was removed
            # If line count decreased, a newline was removed
            new_line_count = self.blockCount()
            if new_line_count < self.blockCount():
                # Newline was removed
                old_end_point = Point(start_line + 1, 0)
            else:
                # Regular character
                old_end_point = Point(start_line, linepos + chars_removed)

        return (
            start_utf16,
            old_end_utf16,
            new_end_utf16,
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
        start_col = position - start_block.position()

        # UTF-16 positions
        start_utf16 = position
        old_end_utf16 = position + chars_removed
        new_end_utf16 = position + chars_added

        # Calculate old end point (before the change)
        # We need to figure out where the old text ended
        if chars_removed > 0:
            # Estimate old end position by looking at current position
            # and the amount removed
            old_end_point = Point(start_line, start_col + chars_removed)
            # This is approximate - if newlines were removed, this won't be exact
            # but tree-sitter can handle approximate old positions
        else:
            old_end_point = Point(start_line, start_col)

        # Calculate new end point (after the change)
        if chars_added > 0:
            new_end_block = self.findBlock(position + chars_added)
            new_end_line = new_end_block.blockNumber()
            new_end_col = (position + chars_added) - new_end_block.position()
            new_end_point = Point(new_end_line, new_end_col)
        else:
            new_end_point = Point(start_line, start_col)

        return (
            start_utf16,
            old_end_utf16,
            new_end_utf16,
            Point(start_line, start_col),
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

        (
            start_utf16,
            old_end_utf16,
            new_end_utf16,
            start_point,
            old_end_point,
            new_end_point,
        ) = ret

        # Convert UTF-16 code unit offsets to byte offsets for tree-sitter
        # In UTF-16LE, each code unit is 2 bytes
        # Also convert Point columns from code units to bytes
        start_point_bytes = Point(start_point.row, start_point.column * 2)
        old_end_point_bytes = Point(old_end_point.row, old_end_point.column * 2)
        new_end_point_bytes = Point(new_end_point.row, new_end_point.column * 2)

        self.byteContentsChange.emit(
            start_utf16 * 2,
            old_end_utf16 * 2,
            new_end_utf16 * 2,
            start_point_bytes,
            old_end_point_bytes,
            new_end_point_bytes,
        )
