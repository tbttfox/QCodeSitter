from Qt.QtGui import QTextDocument, QTextCursor, QTextBlock
from Qt.QtCore import Slot
from .sumrope import SumRope


class SumRopeDocument(QTextDocument):
    """QTextDocument subclass that tracks byte and character counts per line using SumRopes.

    This class maintains two SumRope structures to efficiently track:
    - Character count per QTextBlock/line
    - Byte count (UTF-8) per QTextBlock/line

    These enable fast queries for:
    - Which byte ranges were modified
    - Which character ranges were modified
    - Which line ranges were modified
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Track character count per line
        self._char_rope = SumRope()

        # Track byte count (UTF-8) per line
        self._byte_rope = SumRope()

        # Track the range of lines that have changed
        self._changed_lines_start = None
        self._changed_lines_end = None

        # Initialize with current document content
        self._initialize_ropes()

        # Connect to document changes
        # Use both signals: contentsChange gives us details about what changed,
        # contentsChanged tells us the update is complete
        self.contentsChange.connect(self._on_contents_change)
        self.contentsChanged.connect(self._on_contents_changed)

    def _initialize_ropes(self):
        """Initialize the SumRopes based on current document blocks."""
        char_counts = []
        byte_counts = []

        block = self.firstBlock()
        while block.isValid():
            text = block.text()
            # Include newline in count except for last block
            if block.next().isValid():
                text += '\n'

            char_counts.append(float(len(text)))
            byte_counts.append(float(len(text.encode('utf-8'))))

            block = block.next()

        self._char_rope = SumRope(char_counts)
        self._byte_rope = SumRope(byte_counts)

    @Slot(int, int, int)
    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        """Handle document content changes (fires during change).

        Args:
            position: Character position where change occurred
            chars_removed: Number of characters removed
            chars_added: Number of characters added

        Note: This signal fires DURING the change. We use it to track which
        lines were affected, but we update the ropes in _on_contents_changed
        which fires after the change is complete.
        """
        # Track which lines changed
        # We need to do this here because we have the position/removed/added info
        if chars_removed > 0 or chars_added > 0:
            # The position might be at the end of document during deletion
            doc_len = len(self.toPlainText())
            if doc_len == 0:
                # Empty document
                start_block_num = 0
                end_block_num = 0
            else:
                cursor = QTextCursor(self)
                safe_pos = min(position, max(0, doc_len - 1))
                cursor.setPosition(safe_pos)
                start_block_num = cursor.block().blockNumber()

                # Estimate end block based on the change
                end_pos = min(position + max(chars_removed, chars_added), doc_len)
                if end_pos > 0:
                    cursor.setPosition(min(end_pos, doc_len - 1))
                    end_block_num = cursor.block().blockNumber()
                else:
                    end_block_num = start_block_num

            if self._changed_lines_start is None or self._changed_lines_end is None:
                self._changed_lines_start = start_block_num
                self._changed_lines_end = end_block_num
            else:
                self._changed_lines_start = min(self._changed_lines_start, start_block_num)
                self._changed_lines_end = max(self._changed_lines_end, end_block_num)

    @Slot()
    def _on_contents_changed(self):
        """Handle document content changes (fires after change is complete).

        This signal fires AFTER the document has been updated, so we can
        safely read the current state and update our ropes.
        """
        # Reinitialize ropes from current document state
        self._initialize_ropes()

    def _ensure_synced(self):
        """Ensure ropes are synchronized with document content."""
        current_block_count = self.blockCount()
        if len(self._char_rope) != current_block_count:
            self._initialize_ropes()

    def char_to_byte_offset(self, char_pos: int) -> int:
        """Convert character position to byte offset.

        Args:
            char_pos: Character position in document

        Returns:
            Byte offset corresponding to the character position
        """
        self._ensure_synced()

        # Find which line contains this character position
        line = self.char_to_line(char_pos)

        # Get byte offset to start of this line
        byte_offset = int(self._byte_rope.prefix_sum(line))

        # Get character offset to start of this line
        char_offset = int(self._char_rope.prefix_sum(line))

        # Get the text of this line to calculate offset within line
        block = self.findBlockByNumber(line)
        if block.isValid():
            chars_into_line = char_pos - char_offset
            line_text = block.text()
            if block.next().isValid():
                line_text += '\n'

            # Calculate byte offset within this line
            text_portion = line_text[:chars_into_line]
            bytes_into_line = len(text_portion.encode('utf-8'))
            return byte_offset + bytes_into_line

        return byte_offset

    def char_to_line(self, char_pos: int) -> int:
        """Convert character position to line number (0-indexed).

        Args:
            char_pos: Character position in document

        Returns:
            Line number (0-indexed) containing the character
        """
        self._ensure_synced()

        # Binary search through char_rope to find which line contains char_pos
        left, right = 0, len(self._char_rope)

        while left < right:
            mid = (left + right) // 2
            chars_before = int(self._char_rope.prefix_sum(mid))

            if chars_before <= char_pos:
                left = mid + 1
            else:
                right = mid

        return max(0, left - 1)

    def line_to_char(self, line: int) -> int:
        """Convert line number to character position of line start.

        Args:
            line: Line number (0-indexed)

        Returns:
            Character position where the line starts
        """
        self._ensure_synced()
        return int(self._char_rope.prefix_sum(line))

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

    def get_changed_lines(self) -> tuple[int, int] | None:
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
        return int(self._byte_rope.total_sum())

    def total_chars(self) -> int:
        """Get total number of characters in document."""
        self._ensure_synced()
        return int(self._char_rope.total_sum())

    def total_lines(self) -> int:
        """Get total number of lines in document."""
        self._ensure_synced()
        return len(self._char_rope)
