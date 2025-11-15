from Qt.QtGui import QTextDocument, QTextCursor
from Qt.QtCore import Slot
from .sumrope import SumRope, RLEGroup
from typing import Optional


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

        self.cursor = QTextCursor(self)
        # Track the char/byte offsets per-line
        self._offset_rope: SumRope = SumRope()

        # Track the range of lines that have changed
        self._changed_lines_start: Optional[int] = None
        self._changed_lines_end: Optional[int] = None

        # Initialize with current document content
        self._initialize_ropes()

        # Connect to document changes
        self.contentsChange.connect(self._on_contents_change)

    def build_block_range(self, start: int = 0, count: int = -1) -> list[RLEGroup]:
        """Build the RLE groups for the lines in the given range.
        If no range is given, do the whole document"""
        new_blocks: list[RLEGroup] = []
        block = self.findBlockByNumber(start)
        if not block.isValid():
            return new_blocks
        if count == -1:
            count = self.blockCount() - start

        while block.isValid():
            text = block.text()
            if block.next().isValid():
                text += "\n"

            new_blocks.append(RLEGroup(text))
            if len(new_blocks) >= count:
                next_block = block.next()
                if not next_block.isValid():
                    break

                # If the next block wasn't in our original affected range, we're done
                if block.blockNumber() >= start + count - 1:
                    break
            block = block.next()
        return new_blocks

    def _initialize_ropes(self):
        """Initialize the SumRopes based on current document blocks."""
        self._offset_rope = SumRope(self.build_block_range())

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

        #start_block, _lsum, startPos, _lval, _hist = self._offset_rope.query(position, 0)
        start_block = self.findBlock(position).blockNumber()
        old_end_block, _lsum, oldEndPos, _lval, _hist = self._offset_rope.query(position + chars_removed, 0)
        new_end_block = self.findBlock(position + chars_added).blockNumber()

        rles = self.build_block_range(start_block, new_end_block - start_block + 1)
        self._offset_rope.replace(start_block, old_end_block - start_block + 1, rles)

    def _ensure_synced(self):
        """Ensure ropes are synchronized with document content."""
        if len(self._offset_rope) != self.blockCount():
            self._initialize_ropes()

    def char_to_byte_offset(self, char_pos: int) -> int:
        """Convert character position to byte offset."""
        self._ensure_synced()
        _line, _line_starts, poses, _lval, _hist = self._offset_rope.query(char_pos, 0)
        return poses[1]

    def byte_to_char_offset(self, byte_pos: int) -> int:
        """Convert byte position to character offset."""
        self._ensure_synced()
        _line, _line_starts, poses, _lval, _hist = self._offset_rope.query(byte_pos, 1)
        return poses[0]

    def char_to_line(self, char_pos: int) -> int:
        """Convert character position to line number (0-indexed)."""
        self._ensure_synced()
        line, _line_starts, _poses, _lval, _hist = self._offset_rope.query(char_pos, 0)
        return line

    def line_to_char(self, line: int) -> int:
        """Convert line number to character position of line start."""
        self._ensure_synced()
        return self._offset_rope.prefix_sum(line)[0]

    def line_to_byte(self, line: int) -> int:
        """Convert line number to byte position of line start."""
        self._ensure_synced()
        return self._offset_rope.prefix_sum(line)[1]

    def get_changed_byte_range(self, char_start: int, char_end: int) -> tuple[int, int]:
        """Get byte range corresponding to changed character range.

        Args:
            char_start: Start of character range
            char_end: End of character range (exclusive)

        Returns:
            Tuple of (byte_start, byte_end) offsets
        """
        byte_start = self.char_to_byte_offset(char_start)
        byte_end = self.char_to_byte_offset(char_end)
        return (byte_start, byte_end)

    def get_changed_line_range(self, char_start: int, char_end: int) -> tuple[int, int]:
        """Get line range corresponding to changed character range.

        Args:
            char_start: Start of character range
            char_end: End of character range (exclusive)

        Returns:
            Tuple of (line_start, line_end) where line_end is inclusive
        """
        line_start = self.char_to_line(char_start)

        # For line_end, we need the line containing the last changed character
        if char_end > 0:
            line_end = self.char_to_line(char_end - 1)
        else:
            line_end = 0

        return (line_start, line_end)

    def get_changed_lines(self) -> Optional[tuple[int, int]]:
        """Get the range of lines that have been modified since last reset.

        Returns:
            Tuple of (start_line, end_line) where both are inclusive, or None if no changes

        Note: This tracking works best with operations that emit contentsChange signal
        with parameters (like setPlainText). Some operations like QTextCursor.insertText()
        only emit contentsChanged without parameters, so line tracking may be incomplete
        for those operations. The ropes themselves are always kept up-to-date regardless.
        """
        if self._changed_lines_start is None or self._changed_lines_end is None:
            return None
        return (self._changed_lines_start, self._changed_lines_end)

    def reset_changed_lines(self):
        """Reset the tracking of changed lines."""
        self._changed_lines_start = None
        self._changed_lines_end = None

    def total_bytes(self) -> int:
        """Get total number of bytes in document (UTF-8 encoding)."""
        self._ensure_synced()
        return self._offset_rope.total_sum()[1]

    def total_chars(self) -> int:
        """Get total number of characters in document."""
        self._ensure_synced()
        return self._offset_rope.total_sum()[0]

    def total_lines(self) -> int:
        """Get total number of lines in document."""
        self._ensure_synced()
        return len(self._offset_rope)
