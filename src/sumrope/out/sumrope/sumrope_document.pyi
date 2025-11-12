from .sumrope import RLEGroup as RLEGroup, SumRope as SumRope
from Qt.QtGui import QTextDocument

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
    def __init__(self, parent=None) -> None: ...
    def build_block_range(self, start: int = 0, count: int = -1) -> list[RLEGroup]:
        """Build the RLE groups for the lines in the given range.
        If no range is given, do the whole document"""
    def char_to_byte_offset(self, char_pos: int) -> int:
        """Convert character position to byte offset."""
    def byte_to_char_offset(self, byte_pos: int) -> int:
        """Convert byte position to character offset."""
    def char_to_line(self, char_pos: int) -> int:
        """Convert character position to line number (0-indexed)."""
    def line_to_char(self, line: int) -> int:
        """Convert line number to character position of line start."""
    def line_to_byte(self, line: int) -> int:
        """Convert line number to byte position of line start."""
    def get_changed_byte_range(self, char_start: int, char_end: int) -> tuple[int, int]:
        """Get byte range corresponding to changed character range.

        Args:
            char_start: Start of character range
            char_end: End of character range (exclusive)

        Returns:
            Tuple of (byte_start, byte_end) offsets
        """
    def get_changed_line_range(self, char_start: int, char_end: int) -> tuple[int, int]:
        """Get line range corresponding to changed character range.

        Args:
            char_start: Start of character range
            char_end: End of character range (exclusive)

        Returns:
            Tuple of (line_start, line_end) where line_end is inclusive
        """
    def get_changed_lines(self) -> tuple[int, int] | None:
        """Get the range of lines that have been modified since last reset.

        Returns:
            Tuple of (start_line, end_line) where both are inclusive, or None if no changes

        Note: This tracking works best with operations that emit contentsChange signal
        with parameters (like setPlainText). Some operations like QTextCursor.insertText()
        only emit contentsChanged without parameters, so line tracking may be incomplete
        for those operations. The ropes themselves are always kept up-to-date regardless.
        """
    def reset_changed_lines(self) -> None:
        """Reset the tracking of changed lines."""
    def total_bytes(self) -> int:
        """Get total number of bytes in document (UTF-8 encoding)."""
    def total_chars(self) -> int:
        """Get total number of characters in document."""
    def total_lines(self) -> int:
        """Get total number of lines in document."""
