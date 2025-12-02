import bisect
from math import ceil, floor
from typing import Generator, Optional, Sequence, Any

from Qt.QtWidgets import QPlainTextEdit, QPlainTextDocumentLayout
import numpy as np
from Qt.QtCore import Signal, Slot
from Qt.QtGui import (
    QColor,
    QFont,
    QTextBlock,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from tree_sitter import Language, Parser, Point, Tree, Query, QueryCursor


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

    def set(self, data):
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
    """A subclass of QTextDocument that tracks byte and line changes
    Connect to the `byteContentsChange` signal to get those updates

    Normal typing or deleting one character at a time will provide
    character-level deltas.
    Larger edits like pasting or deleting words will provide line-level
    deltas.
    This is because QT only provides character level change data, and
    we can only accurately infer the size-in-bytes of the characters
    changed when only one character is changed.
    """

    byteContentsChange = Signal(int, int, int, Point, Point, Point)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lay = QPlainTextDocumentLayout(self)
        self.setDocumentLayout(self.lay)

        # Initialize tracker - start with one empty line
        self.tracker: ChunkedLineTracker = ChunkedLineTracker([0])
        self.old_line_count = max(
            1, self.blockCount()
        )  # Qt might report 0 for empty doc
        self.contentsChange.connect(self._on_contents_change)

    def point_to_char(self, point: Point) -> int:
        """Get the document-global character offset of a tsPoint"""
        block = self.findBlockByNumber(point.row)
        btxt = block.text()
        if block.next().isValid():
            btxt += "\n"
        local_c = len(btxt.encode()[: point.column].decode())
        return block.position() + local_c

    def point_to_byte(self, point: Point) -> int:
        """Get the document-global byte offset of a tsPoint"""
        return self.tracker.line_to_byte(point.row) + point.column

    def byte_to_char(self, byteidx: int) -> int:
        """Get the character index for the given byte"""
        line = self.tracker.get_line_for_byte(byteidx)
        line_b = self.tracker.line_to_byte(line)
        col = byteidx - line_b
        return self.point_to_char(Point(line, col))

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

    def _get_common_change_data(self, position, chars_added):
        """Get basic data about a change"""
        start_block = self.findBlock(position)
        new_end_block = self.findBlock(position + chars_added)
        if not new_end_block.isValid():
            new_end_block = self.lastBlock()

        start_line = start_block.blockNumber()
        new_end_line = new_end_block.blockNumber()
        old_line_count = self.old_line_count
        new_line_count = self.blockCount()
        self.old_line_count = new_line_count
        line_delta = new_line_count - old_line_count
        old_end_line = new_end_line - line_delta
        end_is_last = not new_end_block.next().isValid()
        nl_offset = 0 if end_is_last else 1
        return (
            start_block,
            start_line,
            nl_offset,
            line_delta,
            new_end_block,
            old_end_line,
            new_end_line,
            end_is_last,
        )

    def _single_char_change(self, position, chars_added, chars_removed):
        """Handle a single character change, be it one character added, or one removed"""
        (
            start_block,
            start_line,
            nl_offset,
            line_delta,
            new_end_block,
            _old_end_line,
            _new_end_line,
            _end_is_last,
        ) = self._get_common_change_data(position, chars_added)

        curline = start_block.text()
        linepos = position - start_block.position()

        line_start_byte = self.tracker.line_to_byte(start_line)
        line_byte_offset = len(curline[:linepos].encode())
        start_byte = line_start_byte + line_byte_offset
        start_point = Point(start_line, line_byte_offset)
        new_line_bytelen = len(curline.encode()) + nl_offset
        old_line_bytelen = self.tracker.line_bytelength(start_line)

        if chars_removed == 0:
            old_end_byte = start_byte
            old_end_point = start_point
            end_line = start_line + 1
            if line_delta == 0:
                # The character typed was not a newline
                byte_delta = new_line_bytelen - old_line_bytelen
                new_end_byte = old_end_byte + byte_delta
                line_full_bytes = len(curline.encode()) + nl_offset
                new_line_bytelens = [line_full_bytes]
                new_end_point = Point(start_line, line_byte_offset + byte_delta)
            else:
                # The character typed WAS a newline (or empty document case)
                # Check if we actually created a new line or if this is empty document behavior
                # start_block.next() should be the newly created line
                if start_block.next().isValid():
                    # Actually typed a newline - two lines now exist
                    # The line where Enter was pressed now has a newline at the end
                    new_end_byte = start_byte + 1
                    line_full_bytes = (
                        len(curline.encode()) + 1
                    )  # Always +1 for the newline
                    # The next line (start_block.next()) uses nl_offset to determine if IT has a newline
                    next_line_full_bytes = (
                        len(start_block.next().text().encode()) + nl_offset
                    )
                    new_line_bytelens = [line_full_bytes, next_line_full_bytes]
                    new_end_point = Point(start_line + 1, 0)
                else:
                    # Empty document quirk: line_delta=1 but no actual newline
                    byte_delta = new_line_bytelen - old_line_bytelen
                    new_end_byte = old_end_byte + byte_delta
                    new_line_bytelens = [new_line_bytelen]
                    new_end_point = Point(start_line, line_byte_offset + byte_delta)

        else:
            new_end_byte = start_byte
            new_line_bytelens = [new_line_bytelen]
            new_end_point = Point(start_line, line_byte_offset)
            if line_delta == 0:
                # The character removed was not a newline
                byte_delta = new_line_bytelen - old_line_bytelen
                old_end_byte = new_end_byte - byte_delta
                old_end_point = Point(start_line, line_byte_offset - byte_delta)
                end_line = start_line + 1
            else:
                # The character removed WAS a newline
                old_end_byte = new_end_byte + 1
                old_end_point = Point(start_line + 1, 0)
                end_line = start_line + 2

        return (
            start_byte,
            old_end_byte,
            new_end_byte,
            start_point,
            old_end_point,
            new_end_point,
            new_line_bytelens,
            start_line,
            end_line,
        )

    def _multi_char_change(self, position, chars_added, _chars_removed):
        """Handle a multiple character change. Because of how we access byte offsets
        we can only provide line-level granularity for this kind of change
        """
        (
            _start_block,
            start_line,
            _nl_offset,
            _line_delta,
            _new_end_block,
            old_end_line,
            new_end_line,
            end_is_last,
        ) = self._get_common_change_data(position, chars_added)

        new_line_bytelens = [
            len(line.encode())
            for line in self.iter_line_range(start_line, new_end_line + 1)
        ]

        eoff = 0 if end_is_last else 1

        start_byte = self.tracker.line_to_byte(start_line)
        old_end_byte = self.tracker.line_to_byte(old_end_line + 1) - eoff
        old_end_line_bytelen = self.tracker.line_bytelength(old_end_line)
        new_end_byte = start_byte + sum(new_line_bytelens)
        new_end_line_bytelen = new_line_bytelens[-1]

        return (
            start_byte,
            old_end_byte,
            new_end_byte,
            Point(start_line, 0),
            Point(old_end_line, old_end_line_bytelen),
            Point(new_end_line, new_end_line_bytelen),
            new_line_bytelens,
            start_line,
            old_end_line + 1,
        )

    @Slot(int, int, int)
    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        """Handle document content changes incrementally.

        Args:
            position: Character position where change occurred
            chars_removed: Number of characters removed
            chars_added: Number of characters added
        """
        if self.isEmpty():
            return (0, 0, 0, Point(0, 0), Point(0, 0), Point(0, 0))

        # Short-circuit if just doing normal typing and backspacing
        if chars_removed | chars_added == 1 and chars_removed & chars_added == 0:
            ret = self._single_char_change(position, chars_added, chars_removed)
        else:
            ret = self._multi_char_change(position, chars_added, chars_removed)
        (
            start_byte,
            old_end_byte,
            new_end_byte,
            start_point,
            old_end_point,
            new_end_point,
            new_line_bytelens,
            tracker_start_line,
            tracker_end_line,
        ) = ret

        self.tracker.replace_lines(
            tracker_start_line, tracker_end_line, new_line_bytelens
        )
        self.byteContentsChange.emit(
            start_byte,
            old_end_byte,
            new_end_byte,
            start_point,
            old_end_point,
            new_end_point,
        )


class SyntaxHighlighter:
    """Manages syntax highlighting using tree-sitter."""

    def __init__(
        self,
        editor: QPlainTextEdit,
        tree_manager,
        queryStr: str,
        format_specs: dict[str, dict[str, Any]],
    ):
        self.editor = editor
        self.tree_manager = tree_manager
        document = self.editor.document()
        if not isinstance(document, TrackedDocument):
            raise ValueError("This syntax highlighter only works with TrackedDocument")

        document.byteContentsChange.connect(self._on_byte_contents_change)

        self.query = Query(tree_manager.parser.language, queryStr)
        self.query_cursor = QueryCursor(self.query)
        self.format_rules = self.load_format_rules(format_specs)

    @classmethod
    def load_format_rules(
        cls,
        format_specs: dict[str, dict[str, Any]],
    ) -> dict[str, QTextCharFormat]:
        """Load formatting rules for syntax highlighting.

        Format specification: each entry maps a capture name to formatting options.
        Options: color (hex), bold (bool), italic (bool)
        """
        formats = {}
        for name, spec in format_specs.items():
            fmt = QTextCharFormat()
            if "color" in spec:
                fmt.setForeground(QColor(spec["color"]))
            if spec.get("bold", False):
                fmt.setFontWeight(QFont.Bold)
            if spec.get("italic", False):
                fmt.setFontItalic(True)
            if "background" in spec:
                fmt.setBackground(QColor(spec["background"]))
            formats[name] = fmt
        return formats

    def highlight_ranges(self, old_tree: Optional[Tree], new_tree: Tree) -> None:
        """Apply syntax highlighting to changed ranges in the document.

        Args:
            old_tree: Previous tree-sitter parse tree (None if first parse)
            new_tree: New tree-sitter parse tree
        """
        # Get changed ranges
        if old_tree is None:
            # First parse - highlight everything
            root = new_tree.root_node
            changed_ranges = [(0, Point(0, 0), root.end_byte, root.end_point)]
        else:
            changed_ranges = old_tree.changed_ranges(new_tree)
            changed_ranges = [
                (r.start_byte, r.start_point, r.end_byte, r.end_point)
                for r in changed_ranges
            ]

        # Process each changed range
        for start_byte, start_point, end_byte, end_point in changed_ranges:
            self._highlight_range(start_byte, start_point, end_byte, end_point)

    def _highlight_range(
        self,
        start_byte: int,
        start_point: Point,
        end_byte: int,
        end_point: Point,
    ):
        """Highlight a specific byte range in the document."""
        document = self.editor.document()
        if not isinstance(document, TrackedDocument):
            raise ValueError("This syntax highlighter only works with TrackedDocument")

        # Execute the query using QueryCursor
        # Set the byte range for the query
        self.query_cursor.set_byte_range(start_byte, end_byte)

        # Execute the query on the tree's root node
        captures = self.query_cursor.captures(self.tree_manager.tree.root_node)

        # Group formats by block
        from collections import defaultdict
        from Qt.QtGui import QTextLayout

        block_formats = defaultdict(list)

        # Collect all formats for each block
        for capture_name, nodes in captures.items():
            # Get the format for this capture type
            format_obj = self.format_rules.get(capture_name)
            if not format_obj:
                continue
            for node in nodes:
                # Convert byte offsets to character offsets
                node_start_char = document.byte_to_char(node.start_byte)
                node_end_char = document.byte_to_char(node.end_byte)

                # Find which block(s) this spans
                start_block = document.findBlock(node_start_char)
                end_block = document.findBlock(node_end_char)

                block = start_block
                while block.isValid() and block.position() <= end_block.position():
                    block_start = block.position()
                    block_end = block_start + block.length() - 1  # -1 to exclude newline

                    # Calculate range within this block
                    range_start = max(0, node_start_char - block_start)
                    range_length = min(node_end_char, block_end) - max(node_start_char, block_start)

                    if range_length > 0:
                        # Create a QTextLayout.FormatRange
                        fmt_range = QTextLayout.FormatRange()
                        fmt_range.start = range_start
                        fmt_range.length = range_length
                        fmt_range.format = format_obj
                        block_formats[block.blockNumber()].append(fmt_range)

                    block = block.next()

        # Apply formats to each affected block's layout
        # Start from the first block in the changed range
        start_block = document.findBlock(document.point_to_char(start_point))
        end_block = document.findBlock(document.point_to_char(end_point))

        block = start_block
        while block.isValid() and block.position() <= end_block.position():
            layout = block.layout()
            if layout:
                formats = block_formats.get(block.blockNumber(), [])
                layout.setFormats(formats)
                # Trigger a repaint of this block
                document.markContentsDirty(block.position(), block.length())
            block = block.next()

    def _on_byte_contents_change(
        self,
        start_byte: int,
        old_end_byte: int,
        new_end_byte: int,
        start_point: Point,
        old_end_point: Point,
        new_end_point: Point,
    ):
        old_tree = self.tree_manager.tree
        self.tree_manager.update(
            start_byte,
            old_end_byte,
            new_end_byte,
            start_point,
            old_end_point,
            new_end_point,
        )
        self.highlight_ranges(old_tree, self.tree_manager.tree)
