import re
import bisect
from math import ceil, floor
from typing import Generator, Optional, Sequence, Any
import difflib

import numpy as np
from Qt.QtCore import Slot
from Qt.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextBlock,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Point, Tree, Query, QueryCursor
from stransi import Escape, SetAttribute, SetColor
from stransi.attribute import Attribute
from stransi.color import ColorRole

from .hl_groups import FORMAT_SPECS

PY_LANGUAGE = Language(tspython.language())


def load_python_format_rules(
    format_specs: dict[str, dict[str, Any]],
) -> dict[str, QTextCharFormat]:
    """Load formatting rules for Python syntax highlighting.

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
        self.chunk_totals: list[int]
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
        self.chunk_byte_ranges = np.array([0, self.chunk_totals[0]])
        self._rebalance(0)

    def get_chunk_for_line(self, line: int) -> int:
        """Get the index of the chunk containing the given line"""
        return bisect.bisect_right(self.chunk_line_ranges, line) - 1

    def get_chunk_for_byte(self, byteidx: int) -> int:
        """Get the index of the chunk containing the given line"""
        return bisect.bisect_right(self.chunk_byte_ranges, byteidx) - 1

    def get_line_for_byte(self, byteidx: int) -> int:
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

        return np.searchsorted(css, [byteidx - start_byte], "right")[0] - 1

    def line_bytelength(self, line: int) -> int:
        """Get the bytelength of the given line"""
        chunk_idx = self.get_chunk_for_line(line)
        offset = line - self.chunk_line_ranges[chunk_idx]
        return self.chunks[chunk_idx][offset]  # type: ignore

    def total_sum(self) -> int:
        return sum(self.chunk_totals)

    def line_to_byte(self, line: int) -> int:
        """Get the sum of the first `line` lines"""
        chunk_idx = self.get_chunk_for_line(line)
        offset = line - self.chunk_line_ranges[chunk_idx]
        return sum(self.chunk_totals[:chunk_idx]) + np.sum(
            self.chunks[chunk_idx][:offset]
        )

    def range_sum(self, start: int, end: int) -> int:
        """Get the sum of the values between start and end"""
        return self.line_to_byte(end) - self.line_to_byte(start)

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

        # Get the chunk range.  end_chunk_idx is *INCLUSIVE*
        start_chunk_idx = self.get_chunk_for_line(start_line)
        end_chunk_idx = self.get_chunk_for_line(post_line - 1)

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


class SingleLineHighlighter(QSyntaxHighlighter):
    """A QSyntaxHighlighter that formats a single line"""

    # Regex to match common ANSI escape sequences
    ansi_splitter = re.compile(r"(\x1b\[[0-9;]*m)")
    byte_splitter = re.compile(
        r"[\x00-\x7f]+|[\x80-\u07ff]+|[\u0800-\uffff]+|[\U00010000-\U0010ffff]+"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.format_rules = load_python_format_rules(FORMAT_SPECS)
        self.language = Language(tspython.language())
        self.parser = Parser(self.language)
        self.query = Query(self.language, tspython.HIGHLIGHTS_QUERY)
        self.query_cursor = QueryCursor(self.query)

    def build_charmap(self, text):
        """Build a mapping from byte index to character index as a list"""
        charmap = []
        charidx = 0
        for seg in self.byte_splitter.findall(text):
            bytesize = len(seg[0].encode())
            charcount = len(seg)
            for _ in range(charcount):
                charmap.extend([charidx] * bytesize)
                charidx += 1
        return charmap

    def extract_ansi(self, text: str) -> tuple[str, list[tuple[str, int, int]]]:
        """Extract the ansi codes from some text, keeping track of their character offsets"""
        sp = self.ansi_splitter.split(text)
        curidx = 0
        codes = []
        chunks = []
        curcode = ("\033[0m", 0)
        for i, seg in enumerate(sp):
            if i % 2:  # Ansi code
                curcode = (seg, curidx)
            else:  # regular text
                chunks.append(text)
                curidx += len(text)
                codes.append((curcode[0], curcode[1], curidx))
        return "".join(chunks), codes

    def highlightBlock(self, text: str):
        """Apply highlighting to a single block (line)"""
        text, ansi = self.extract_ansi(text)
        bstr = text.encode()
        tree = self.parser.parse(bstr)
        self.query_cursor.set_byte_range(0, tree.root_node.end_byte)
        captures = self.query_cursor.captures(tree.root_node)
        charmap = self.build_charmap(text)

        # Apply formatting for each capture
        for capture_name, nodes in captures.items():
            # Get the format for this capture type
            format_obj = self.format_rules.get(capture_name)
            if not format_obj:
                continue
            for node in nodes:
                # Convert byte offsets to character offsets
                startchar = charmap[node.start_byte]
                endchar = charmap[node.end_byte]
                self.setFormat(startchar, endchar - startchar, format_obj)

        current_format = QTextCharFormat()
        for codes, start, end in ansi:
            for s in Escape(codes).instructions():
                if isinstance(s, SetAttribute):
                    if s.attribute == Attribute.NORMAL:
                        current_format = QTextCharFormat()
                    elif s.attribute == Attribute.BOLD:
                        current_format.setFontWeight(QFont.Weight.Bold)
                    elif s.attribute == Attribute.DIM:
                        current_format.setFontWeight(QFont.Weight.Light)
                    elif s.attribute == Attribute.NEITHER_BOLD_NOR_DIM:
                        current_format.setFontWeight(QFont.Weight.Normal)
                    elif s.attribute == Attribute.ITALIC:
                        current_format.setFontItalic(True)
                    elif s.attribute == Attribute.NOT_ITALIC:
                        current_format.setFontItalic(False)
                    elif s.attribute == Attribute.UNDERLINE:
                        current_format.setFontUnderline(True)
                    elif s.attribute == Attribute.NOT_UNDERLINE:
                        current_format.setFontUnderline(False)
                elif isinstance(s, SetColor):
                    if s.color is not None:
                        ocolor = s.color.rgb
                        color = QColor.fromRgbF(ocolor.red, ocolor.green, ocolor.blue)
                        if s.role == ColorRole.FOREGROUND:
                            current_format.setForeground(color)
                        elif s.role == ColorRole.BACKGROUND:
                            current_format.setBackground(color)
            self.setFormat(start, end - start, current_format)


class PythonSyntaxHighlighter:
    """Manages syntax highlighting for Python code using tree-sitter."""

    def __init__(
        self, language: Language, document: QTextDocument, tracker: ChunkedLineTracker
    ):
        self.language: Language = language
        self.document: QTextDocument = document
        self.tracker: ChunkedLineTracker = tracker

        self.query = Query(language, tspython.HIGHLIGHTS_QUERY)
        self.query_cursor = QueryCursor(self.query)

        self.format_rules = self.load_python_format_rules(FORMAT_SPECS)

    def point_to_char(self, point: Point) -> int:
        """Get the document-global character offset of a tsPoint"""
        block = self.document.findBlockByNumber(point.row)
        btxt = block.text()
        if block.next().isValid():
            btxt += "\n"
        local_c = len(btxt.encode()[: point.column].decode())
        return block.position() + local_c

    def point_to_byte(self, point: Point) -> int:
        """Get the document-global byte offset of a tsPoint"""
        return self.tracker.line_to_byte(point.row) + point.column

    def byte_to_char(self, byteidx):
        line = self.tracker.get_line_for_byte(byteidx)
        line_b = self.tracker.line_to_byte(line)
        return self.point_to_char(Point(line, byteidx - line_b))

    @classmethod
    def load_python_format_rules(
        cls,
        format_specs: dict[str, dict[str, Any]],
    ) -> dict[str, QTextCharFormat]:
        """Load formatting rules for Python syntax highlighting.

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
            self._highlight_range(
                new_tree, start_byte, start_point, end_byte, end_point
            )

    def _highlight_range(
        self,
        tree: Tree,
        start_byte: int,
        start_point: Point,
        end_byte: int,
        end_point: Point,
    ):
        """Highlight a specific byte range in the document."""
        # txt = self.document.toPlainText()
        # bbb = txt.encode()

        # Clear formatting in this range first
        start_char = self.point_to_char(start_point)
        end_char = self.point_to_char(end_point)

        clear_format = QTextCharFormat()
        cursor = QTextCursor(self.document)
        cursor.setPosition(start_char)
        cursor.setPosition(end_char, QTextCursor.KeepAnchor)
        cursor.setCharFormat(clear_format)

        # Execute the query using QueryCursor
        # Set the byte range for the query
        self.query_cursor.set_byte_range(start_byte, end_byte)

        # Execute the query on the tree's root node
        captures = self.query_cursor.captures(tree.root_node)

        # Apply formatting for each capture
        for capture_name, nodes in captures.items():
            # Get the format for this capture type
            format_obj = self.format_rules.get(capture_name)
            if not format_obj:
                continue
            for node in nodes:
                # Convert byte offsets to character offsets
                node_start_char = self.byte_to_char(node.start_byte)
                node_end_char = self.byte_to_char(node.end_byte)

                # trn = txt[node_start_char:node_end_char].encode()
                # brn = bbb[node.start_byte : node.end_byte]

                # Apply the format
                cursor = QTextCursor(self.document)
                cursor.setPosition(node_start_char)
                cursor.setPosition(node_end_char, QTextCursor.KeepAnchor)
                cursor.setCharFormat(format_obj)


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
        self._ts_prediction: dict[int, QTextBlock] = {}

        self.cursor = QTextCursor(self)
        self.old_line_count = 0
        self.old_char_count = 0
        self.tracker = ChunkedLineTracker()

        self.highlighter = PythonSyntaxHighlighter(PY_LANGUAGE, self, self.tracker)

        self.parser = Parser(PY_LANGUAGE)
        self.tree = self.parser.parse(self.treesitter_callback)

        self.contentsChange.connect(self._on_contents_change)

        self._prev = ""

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

    def _test_diff(self):
        prevtext = self._prev
        curtext = self.toPlainText()
        self._prev = curtext
        changes = difflib.ndiff(prevtext, curtext)
        output_list = [(i, li) for i, li in enumerate(changes) if li[0] != " "]
        print("DIFF", output_list)

    def _get_common_change_data(self, position, chars_added):
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
                # The character typed WAS a newline
                new_end_byte = start_byte + 1
                line_full_bytes = len(curline.encode()) + 1
                next_line_full_bytes = (
                    len(new_end_block.next().text().encode()) + nl_offset
                )
                new_line_bytelens = [line_full_bytes, next_line_full_bytes]
                new_end_point = Point(start_line + 1, 0)

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

        self.tracker.replace_lines(start_line, end_line, new_line_bytelens)
        self.tree.edit(
            start_byte=start_byte,
            old_end_byte=old_end_byte,
            new_end_byte=new_end_byte,
            start_point=start_point,
            old_end_point=old_end_point,
            new_end_point=new_end_point,
        )
        old_tree = self.tree
        self.tree = self.parser.parse(self.treesitter_callback, old_tree)
        self.highlighter.highlight_ranges(old_tree, self.tree)

    def _multi_char_change(self, position, chars_added, _chars_removed):
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

        if end_is_last:
            old_end_byte = self.tracker.total_sum()
        else:
            old_end_byte = self.tracker.line_to_byte(old_end_line + 1)

        self.tracker.replace_lines(start_line, old_end_line + 1, new_line_bytelens)

        if end_is_last:
            new_end_byte = self.tracker.total_sum()
        else:
            new_end_byte = self.tracker.line_to_byte(new_end_line + 1)
        start_byte = self.tracker.line_to_byte(start_line)

        self.tree.edit(
            start_byte=start_byte,
            old_end_byte=old_end_byte,
            new_end_byte=new_end_byte,
            start_point=Point(start_line, 0),
            old_end_point=Point(old_end_line + 1, 0),
            new_end_point=Point(new_end_line + 1, 0),
        )

        old_tree = self.tree
        self.tree = self.parser.parse(self.treesitter_callback, old_tree)
        self.highlighter.highlight_ranges(old_tree, self.tree)

    @Slot(int, int, int)
    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        """Handle document content changes incrementally.

        Args:
            position: Character position where change occurred
            chars_removed: Number of characters removed
            chars_added: Number of characters added
        """
        self._ts_prediction = {}
        if self.isEmpty():
            self.old_line_count = 1
            self.tracker.set([0])
            self.tree = self.parser.parse(self.treesitter_callback)
            self._ts_prediction: dict[int, QTextBlock] = {}
            return

        # Short-circuit if just doing normal typing and backspacing
        if chars_removed | chars_added == 1 and chars_removed & chars_added == 0:
            self._single_char_change(position, chars_added, chars_removed)
        else:
            self._multi_char_change(position, chars_added, chars_removed)

    def treesitter_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """A callback to pass to the tree-sitter `Parser` constructor
        for efficient access to the underlying byte data without duplicating it
        """
        curblock: Optional[QTextBlock] = self._ts_prediction.get(ts_point.row)
        if curblock is None:
            try:
                curblock = self.findBlockByNumber(ts_point.row)
            except IndexError:
                self._ts_prediction = {}
                return b""

        self._ts_prediction[ts_point.row] = curblock
        nxt = curblock.next()
        self._ts_prediction[ts_point.row + 1] = nxt
        suffix = b"\n" if nxt.isValid() else b""
        linebytes = curblock.text().encode() + suffix

        return linebytes[ts_point.column :]
