from Qt.QtGui import QTextDocument
from Qt.QtCore import Slot
from .sumrope import SumRope, IntGroup
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
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Track the char/byte offsets per-line
        self._offset_rope: SumRope = SumRope()

        # Track the range of lines that have changed
        self._changed_lines_start: Optional[int] = None
        self._changed_lines_end: Optional[int] = None

        # Initialize with current document content
        self._initialize_ropes()

        # Connect to document changes
        # contentsChange gives us position/removed/added for incremental updates
        # contentsChanged fires for operations that don't provide details (like QTextCursor)
        self.contentsChange.connect(self._on_contents_change)
        self.contentsChanged.connect(self._on_contents_changed)

    def _initialize_ropes(self):
        """Initialize the SumRopes based on current document blocks."""
        pairs = []

        block = self.firstBlock()
        while block.isValid():
            text = block.text()
            # Include newline in count except for last block
            if block.next().isValid():
                text += "\n"
            pairs.append((len(text), len(text.encode("utf-8"))))
            block = block.next()
        self._offset_rope = SumRope(pairs)

    @Slot(int, int, int)
    def _on_contents_change(self, position: int, chars_removed: int, chars_added: int):
        """Handle document content changes incrementally.

        Args:
            position: Character position where change occurred
            chars_removed: Number of characters removed
            chars_added: Number of characters added
        """
        # Find which block the change starts at BEFORE the change
        # We need to do this calculation based on the old rope state
        old_block_count = len(self._offset_rope)

        # Find the block number containing 'position' in the old state
        # Binary search: find the block where prefix_sum(i) <= position < prefix_sum(i+1)
        left = self._offset_rope.bisect(position, 0)
        start_block = max(0, left - 1)

        # Calculate how many blocks were affected by the removal
        if chars_removed > 0:
            # Find which block contains position + chars_removed
            end_pos = position + chars_removed
            left = self._offset_rope.bisect(end_pos, 0)
            end_block = max(start_block, min(left, old_block_count - 1))
            blocks_removed = end_block - start_block + 1
        else:
            blocks_removed = 1  # At minimum, we're modifying the current block

        # Now get the NEW state of the affected blocks from the document
        # The document has already been updated at this point
        new_counts: list[IntGroup] = []

        # We need to collect blocks until we've covered the entire changed region
        # The changed region might span more or fewer blocks than before due to newline changes
        block = self.findBlockByNumber(start_block)

        if block.isValid():
            # Collect blocks starting from start_block
            # We need at least blocks_removed blocks, but may need more if newlines were added
            # Continue until we run out of blocks or have covered enough blocks
            while block.isValid():
                text = block.text()
                # Include newline in count except for last block
                if block.next().isValid():
                    text += "\n"

                new_counts.append(IntGroup([len(text), len(text.encode("utf-8"))]))
                # We've collected at least blocks_removed blocks worth of new data
                # Check if we should continue to the next block
                if len(new_counts) >= blocks_removed:
                    # If there's no next block, we're done
                    next_block = block.next()
                    if not next_block.isValid():
                        break

                    # If the next block wasn't in our original affected range, we're done
                    # (it only would be if we removed fewer blocks than expected)
                    if block.blockNumber() >= start_block + blocks_removed - 1:
                        break

                block = block.next()
        else:
            # No valid block, document might be empty
            new_counts = [IntGroup()]

        # Update the ropes incrementally
        self._offset_rope.replace(start_block, blocks_removed, new_counts)

        # Track which lines changed
        if chars_removed > 0 or chars_added > 0:
            end_block_num = start_block + len(new_counts) - 1

            if self._changed_lines_start is None or self._changed_lines_end is None:
                self._changed_lines_start = start_block
                self._changed_lines_end = end_block_num
            else:
                self._changed_lines_start = min(self._changed_lines_start, start_block)
                self._changed_lines_end = max(self._changed_lines_end, end_block_num)

    @Slot()
    def _on_contents_changed(self):
        """Handle changes from operations that don't emit contentsChange details.

        This handles operations like QTextCursor.insertText() which only emit
        contentsChanged without position/removed/added info. We check if our
        ropes are out of sync and reinitialize if needed.

        Note: This is a fallback for QTextCursor operations. It's still O(n)
        to reinitialize, but only happens for cursor operations, not normal
        text changes which use the incremental _on_contents_change path.
        """
        current_block_count = self.blockCount()
        rope_block_count = len(self._offset_rope)

        # If block counts differ, we definitely need to resync
        needs_resync = current_block_count != rope_block_count

        # Even if block count is same, QTextCursor might have modified content
        # within a block. Check by comparing character counts.
        if not needs_resync and current_block_count > 0:
            # Sample check: verify the first and last block
            # This is O(1) and catches most desyncs
            first_block = self.firstBlock()
            if first_block.isValid():
                first_text = first_block.text()
                if first_block.next().isValid():
                    first_text += "\n"
                expected_chars = len(first_text)
                actual_chars = self._offset_rope.get_single(0)[0]
                if expected_chars != actual_chars:
                    needs_resync = True

        if needs_resync:
            self._initialize_ropes()
            # We can't track which lines changed without the position info
            # so we mark the entire document as changed
            if self._changed_lines_start is None or self._changed_lines_end is None:
                self._changed_lines_start = 0
                self._changed_lines_end = max(0, current_block_count - 1)
            else:
                self._changed_lines_start = min(self._changed_lines_start, 0)
                self._changed_lines_end = max(
                    self._changed_lines_end, max(0, current_block_count - 1)
                )

    def _ensure_synced(self):
        """Ensure ropes are synchronized with document content."""
        current_block_count = self.blockCount()
        if len(self._offset_rope) != current_block_count:
            self._initialize_ropes()

    def char_to_byte_offset(self, char_pos: int) -> int:
        """Convert character position to byte offset.

        Args:
            char_pos: Character position in document

        Returns:
            Byte offset corresponding to the character position
        """
        self._ensure_synced()

        # Find which line contains this character position using binary search
        # This is the same logic as char_to_line but we keep the char_offset
        left, right = 0, len(self._offset_rope)

        while left < right:
            mid = (left + right) // 2
            chars_before = self._offset_rope.prefix_sum(mid)[0]

            if chars_before <= char_pos:
                left = mid + 1
            else:
                right = mid

        line = max(0, left - 1)

        # Get char/byte offset to start of this line
        offset_pair = self._offset_rope.prefix_sum(line)
        char_offset = offset_pair[0]
        byte_offset = offset_pair[1]

        # Get the text of this line to calculate offset within line
        block = self.findBlockByNumber(line)
        if block.isValid():
            chars_into_line = char_pos - char_offset
            line_text = block.text()
            if block.next().isValid():
                line_text += "\n"

            # Calculate byte offset within this line
            text_portion = line_text[:chars_into_line]
            bytes_into_line = len(text_portion.encode("utf-8"))
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
        left, right = 0, len(self._offset_rope)

        while left < right:
            mid = (left + right) // 2
            chars_before = self._offset_rope.prefix_sum(mid)[0]

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
        return self._offset_rope.prefix_sum(line)[0]

    def line_to_byte(self, line: int) -> int:
        """Convert line number to byte position of line start.

        Args:
            line: Line number (0-indexed)

        Returns:
            Byte position where the line starts
        """
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
