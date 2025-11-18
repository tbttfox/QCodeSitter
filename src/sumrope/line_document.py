from Qt.QtGui import QTextDocument, QTextCursor, QTextBlock
from Qt.QtCore import Slot
from typing import Generator, Optional, Sequence

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Point

from math import ceil, floor, log
import numpy as np
import bisect

PY_LANGUAGE = Language(tspython.language())


def _zcs(ary) -> np.ndarray:
    """leading Zero Cumulative Summation"""
    return np.concatenate(([0], np.cumsum(ary)))


class ChunkedLineTracker:
    def __init__(self, chunk_size: int = 10000):
        self.chunk_size = chunk_size
        self.chunks = []
        self.chunk_cumsums: list[Optional[np.ndarray]] = []
        self.chunk_totals = []
        self.chunk_ranges = []

    def get_chunk_for_line(self, line: int) -> int:
        """Get the index of the chunk containing the given line"""
        return bisect.bisect_right(self.chunk_ranges, line) - 1

    def get_line_for_character(self, charidx: int) -> int:
        """Get the line that contains the given character index"""
        chunk_idx = None
        offset = charidx
        for i, tot in enumerate(self.chunk_totals):
            if offset < tot:
                chunk_idx = i
                break
            offset -= tot
        if chunk_idx is None:
            raise IndexError("Character index out of range")

        css = self.chunk_cumsums[chunk_idx]
        if css is None:
            css = _zcs(self.chunks[chunk_idx])
            self.chunk_cumsums[chunk_idx] = css

        return np.searchsorted(css, [offset], "right")[0] - 1

    def total_sum(self) -> int:
        return sum(self.chunk_totals)

    def prefix_sum(self, count: int) -> int:
        """Get the sum of the first `count` lines"""
        chunk_idx = self.get_chunk_for_line(count)
        offset = self.chunk_ranges[chunk_idx] - count
        return sum(self.chunk_totals[:chunk_idx]) + np.sum(
            self.chunks[chunk_idx][:offset]
        )

    def range_sum(self, start: int, end: int) -> int:
        """Get the sum of the values between start and end"""
        return self.prefix_sum(end) - self.prefix_sum(start)

    def replace_lines(
        self, start_line: int, end_line: int, new_line_lengths: Sequence[int]
    ):
        """Replace the INCLUSIVE range of lines with the given new line lengths
        Meaning I'm replacing this range of lines `range(start_line, end_line + 1)`
        """
        assert end_line >= start_line

        if not self.chunks:
            new_chunk = np.array(new_line_lengths)
            self.chunks = [new_chunk]
            self.chunk_cumsums = [None]
            self.chunk_totals = [np.sum(new_chunk)]
            self.chunk_ranges = _zcs([len(c) for c in self.chunks])
            self._rebalance(0)
            return

        start_chunk_idx = self.get_chunk_for_line(start_line)
        end_chunk_idx = self.get_chunk_for_line(end_line)

        start_offset = self.chunk_ranges[start_chunk_idx] - start_line
        end_offset = self.chunk_ranges[end_chunk_idx] - end_line

        pre_chunk = self.chunks[start_chunk_idx][:start_offset]
        post_chunk = self.chunks[end_chunk_idx][end_offset:]

        new_chunk = np.concatenate((pre_chunk, new_line_lengths, post_chunk))
        self.chunks[start_chunk_idx : end_chunk_idx + 1] = [new_chunk]
        self.chunk_cumsums[start_chunk_idx : end_chunk_idx + 1] = [None]
        self.chunk_totals[start_chunk_idx : end_chunk_idx + 1] = [np.sum(new_chunk)]
        chunk_lengths = [len(c) for c in self.chunks]
        self.chunk_ranges = _zcs(chunk_lengths)
        self._rebalance(start_chunk_idx)

    def _merge_chunk_with_right(self, left_idx: int):
        """Merge a chunk with the chunk to its right"""
        new_chunk = np.concatenate((self.chunks[left_idx], self.chunks[left_idx + 1]))
        new_total = np.sum(new_chunk)
        self.chunks[left_idx : left_idx + 2] = [new_chunk]
        self.chunk_cumsums[left_idx : left_idx + 2] = [None]
        self.chunk_totals[left_idx : left_idx + 2] = [new_total]
        chunk_lengths = [len(c) for c in self.chunks]
        self.chunk_ranges = _zcs(chunk_lengths)

    def _get_nice_counts(self, totalsize, num_chunks):
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
        self.chunk_ranges = _zcs(chunk_lengths)

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


class SumRopeDocument(QTextDocument):
    """QTextDocument subclass that tracks byte and character counts per line using SumRopes.

    This class maintains two SumRope structures to efficiently track:
    - Character count per QTextBlock/line
    - Byte count (UTF-8) per QTextBlock/line

    These enable fast queries for:
    - Which byte ranges were modified
    - Which character ranges were modified
    - Which line ranges were modified

    NOTE:
    If anything is changed programmatically using a QTextCursor, it is up to the programmer
    to properly tell this document what range changed.
    I don't actually know how to do that yet. It'll probably require new functions
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ts_row_prediction: Optional[QTextBlock] = None
        self._ts_row_num_prediction: Optional[int] = None
        self.cursor = QTextCursor(self)
        self.old_line_count = 0
        self.old_char_count = 0
        self.tracker = ChunkedLineTracker()

        self.parser = Parser(PY_LANGUAGE)
        self.tree = self.parser.parse(self.treesitter_callback)

        self.contentsChange.connect(self._on_contents_change)

    def iter_line_range(
        self, start: int = 0, count: int = -1
    ) -> Generator[str, None, None]:
        """Build the RLE groups for the lines in the given range.
        If no range is given, do the whole document"""
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

    def get_char_range(self, start: int, count: int) -> str:
        self.cursor.setPosition(start)
        self.cursor.setPosition(start + count, QTextCursor.KeepAnchor)
        return self.cursor.selectedText()

    @Slot(int, int, int)
    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        """Handle document content changes incrementally.

        Args:
            position: Character position where change occurred
            chars_removed: Number of characters removed
            chars_added: Number of characters added
        """
        start_block = self.findBlock(position)
        new_end_block = self.findBlock(position + chars_added)

        start_line = start_block.blockNumber()
        new_end_line = new_end_block.blockNumber()

        end_is_last = not new_end_block.next().isValid()

        old_line_count = self.old_line_count
        new_line_count = self.blockCount()
        self.old_line_count = new_line_count

        line_delta = new_line_count - old_line_count
        old_end_line = new_end_line + line_delta

        new_line_bytelens = [
            len(line.encode("utf8"))
            for line in self.iter_line_range(start_line, new_end_line)
        ]
        if end_is_last:
            old_end_byte = self.tracker.total_sum()
        else:
            old_end_byte = self.tracker.prefix_sum(old_end_line + 1)
        self.tracker.replace_lines(start_line, old_end_line, new_line_bytelens)
        if end_is_last:
            new_end_byte = self.tracker.total_sum()
        else:
            new_end_byte = self.tracker.prefix_sum(new_end_line + 1)

        start_byte = self.tracker.prefix_sum(start_line)

        self.tree.edit(
            start_byte=start_byte,
            old_end_byte=old_end_byte,
            new_end_byte=new_end_byte,
            start_point=(start_line, 0),
            old_end_point=(old_end_line + 1, 0),
            new_end_point=(new_end_line + 1, 0),
        )
        old_tree = self.tree
        self.tree = self.parser.parse(self.treesitter_callback, old_tree)

        # TODO: apply the changed ranges

    def treesitter_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """A callback to pass to the tree-sitter `Parser` constructor
        for efficient access to the underlying byte data without duplicating it
        """
        curblock: Optional[QTextBlock] = None
        if self._ts_row_num_prediction is not None:
            if self._ts_row_num_prediction == ts_point.row:
                curblock = self._ts_row_prediction

        if curblock is None:
            try:
                curblock = self.findBlockByNumber(ts_point.row)
            except IndexError:
                self._ts_row_prediction = None
                self._ts_row_num_prediction = None
                return b""

        # Guess the next line to be requested by treesitter
        self._ts_row_num_prediction = ts_point.row + 1
        self._ts_row_prediction = curblock.next()

        linebytes = curblock.text().encode("utf8")
        return linebytes[ts_point.column :]
