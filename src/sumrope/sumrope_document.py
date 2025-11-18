from Qt.QtGui import QTextDocument, QTextCursor, QTextBlock
from Qt.QtCore import Slot
from .sumrope import SumRope, RLEGroup
from typing import Generator


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

        # Initialize with current document content
        self._initialize_ropes()

        # Connect to document changes
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

    def build_block_range(self, start: int = 0, count: int = -1) -> list[RLEGroup]:
        """Build the RLE groups for the lines in the given range.
        If no range is given, do the whole document"""
        return [RLEGroup(line) for line in self.iter_line_range(start, count)]

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

        start_line, _lsum, start_pos, _lval = self._offset_rope.query(position, 0)
        old_end_line, _lsum, old_end_pos, _lval = self._offset_rope.query(position + chars_removed, 0)

        new_end_block_num = self.findBlock(position + chars_added).blockNumber()
        rles = self.build_block_range(start_line, new_end_block_num - start_line + 1)
        self._offset_rope.replace(start_line, old_end_line - start_line + 1, rles)

        new_end_line, _lsum, new_end_pos, _lval = self._offset_rope.query(position + chars_added, 0)





