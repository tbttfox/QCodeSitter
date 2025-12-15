from __future__ import annotations
from Qt.QtGui import QKeyEvent, QTextCursor
from Qt.QtCore import Qt
from typing import TYPE_CHECKING
from . import Behavior, HasKeyPress

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


class AutoBracket(HasKeyPress, Behavior):
    """Automatically inserts closing brackets, quotes, and other paired characters"""

    # Map of opening characters to their closing pairs
    PAIRS = {
        "(": ")",
        "[": "]",
        "{": "}",
        '"': '"',
        "'": "'",
        "`": "`",
    }

    # Characters that should skip over the closing character instead of inserting
    SKIP_CHARS = {")", "]", "}", '"', "'", "`"}

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.enabled = True
        self.setListen({"auto_bracket_enabled"})

    def updateOptions(self, keys):
        super().updateOptions(keys)
        if "auto_bracket_enabled" in keys:
            self.enabled = self.options.get("auto_bracket_enabled", True)

    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        if not self.enabled:
            return False

        # Check if multi-cursor mode is active
        if self.editor.multi_cursor_manager.is_active():
            text = event.text()
            if text and len(text) == 1:
                char = text[0]
                # Handle inserting opening character with its pair
                if char in self.PAIRS:
                    return self._insert_pair_multi_cursor(char)
                # Note: skipping and backspace deletion in multi-cursor mode
                # will be handled by the multi-cursor manager itself
            return False

        text = event.text()
        if not text or len(text) != 1:
            return False

        char = text[0]
        cursor = self.editor.textCursor()

        # Handle inserting opening character with its pair
        if char in self.PAIRS:
            return self._insert_pair(cursor, char)

        # Handle skipping over closing character
        if char in self.SKIP_CHARS:
            return self._skip_closing(cursor, char)

        # Handle backspace to delete pairs
        if event.key() == Qt.Key_Backspace:
            return self._delete_pair(cursor)

        return False

    def _insert_pair(self, cursor: QTextCursor, open_char: str) -> bool:
        """Insert opening character and its closing pair"""
        close_char = self.PAIRS[open_char]

        # Handle triple-quotes for Python
        if open_char in ('"', "'"):
            triple_quote_result = self._handle_triple_quote(cursor, open_char)
            if triple_quote_result is not None:
                return triple_quote_result

        # For quotes, check if we should skip instead of insert
        if open_char in ('"', "'", "`") and self._should_skip_quote(cursor, open_char):
            return self._skip_closing(cursor, open_char)

        # Check if there's a selection - if so, wrap it
        if cursor.hasSelection():
            return self._wrap_selection(cursor, open_char, close_char)

        # Insert the pair
        cursor.beginEditBlock()
        cursor.insertText(open_char + close_char)
        cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 1)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        return True

    def _handle_triple_quote(self, cursor: QTextCursor, quote: str) -> bool | None:
        """Handle triple-quote insertion and skipping for Python docstrings

        Returns:
            True if triple-quote was handled (inserted or skipped)
            False if we should fall through to normal quote handling
            None if we shouldn't handle this event at all
        """
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()

        # Check if we already have two quotes before cursor
        # Two cases:
        # 1. User typed two quotes manually: text[col-2:col] == quote*2
        # 2. User typed one quote, auto-pair inserted second: text[col-1] == quote and text[col] == quote
        before_two = col >= 2 and text[col-2:col] == quote * 2
        before_one_after_one = (col >= 1 and col < len(text) and
                                text[col-1] == quote and text[col] == quote)

        if before_two and not before_one_after_one:
            # Case 1: User typed two quotes, now typing third
            # Insert the opening third quote and three closing quotes
            cursor.beginEditBlock()
            cursor.insertText(quote + quote * 3)
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 3)
            cursor.endEditBlock()
            self.editor.setTextCursor(cursor)
            return True
        elif before_one_after_one:
            # Case 2: User typed one quote (auto-paired to two), now typing second
            # Check if there's another quote before the auto-paired quotes
            if col >= 2 and text[col-2] == quote:
                # We have: qq|q (where | is cursor, q is quote)
                # User is typing the third quote
                # Delete the auto-paired closing quote and insert triple-quote pair
                cursor.beginEditBlock()
                cursor.deleteChar()  # Remove the auto-paired quote
                cursor.insertText(quote + quote * 3)  # Add opening third + closing three
                cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 3)
                cursor.endEditBlock()
                self.editor.setTextCursor(cursor)
                return True

        # Check if we're about to skip over triple-quotes
        if col + 2 < len(text) and text[col:col+3] == quote * 3:
            # Next three characters are the same quote - skip all three
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 3)
            self.editor.setTextCursor(cursor)
            return True

        # Not a triple-quote situation
        return None

    def _should_skip_quote(self, cursor: QTextCursor, quote: str) -> bool:
        """Determine if we should skip over a quote instead of inserting a pair"""
        # Get character after cursor
        pos = cursor.position()
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()

        # If next character is the same quote, skip over it
        if col < len(text) and text[col] == quote:
            return True

        return False

    def _wrap_selection(self, cursor: QTextCursor, open_char: str, close_char: str) -> bool:
        """Wrap the current selection with the pair"""
        selected_text = cursor.selectedText()

        cursor.beginEditBlock()
        cursor.insertText(open_char + selected_text + close_char)
        cursor.endEditBlock()

        # Move cursor to after the opening character
        cursor.setPosition(cursor.position() - len(selected_text) - 1)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(selected_text))
        self.editor.setTextCursor(cursor)
        return True

    def _skip_closing(self, cursor: QTextCursor, char: str) -> bool:
        """Skip over a closing character if it's already there"""
        pos = cursor.position()
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()

        # Check if the character after cursor matches
        if col < len(text) and text[col] == char:
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 1)
            self.editor.setTextCursor(cursor)
            return True

        return False

    def _delete_pair(self, cursor: QTextCursor) -> bool:
        """Delete both characters of a pair when backspacing"""
        if cursor.hasSelection():
            return False

        pos = cursor.position()
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()

        # Check for triple-quote deletion
        if col >= 3 and col + 3 <= len(text):
            before_triple = text[col-3:col]
            after_triple = text[col:col+3]
            # Check if we're between triple-quotes
            if before_triple in ('"""', "'''") and before_triple == after_triple:
                cursor.beginEditBlock()
                # Delete the three before
                for _ in range(3):
                    cursor.deletePreviousChar()
                # Delete the three after
                for _ in range(3):
                    cursor.deleteChar()
                cursor.endEditBlock()
                self.editor.setTextCursor(cursor)
                return True

        # Check if we're between a pair
        if col > 0 and col < len(text):
            before = text[col - 1]
            after = text[col]

            # Check if it's a matching pair
            if before in self.PAIRS and self.PAIRS[before] == after:
                cursor.beginEditBlock()
                cursor.deletePreviousChar()  # Delete opening char
                cursor.deleteChar()  # Delete closing char
                cursor.endEditBlock()
                self.editor.setTextCursor(cursor)
                return True

        return False

    def _insert_pair_multi_cursor(self, open_char: str) -> bool:
        """Insert opening character and its closing pair at all cursors"""
        close_char = self.PAIRS[open_char]

        # Get primary cursor before sorting
        primary = self.editor.multi_cursor_manager.get_primary_cursor()
        all_cursors = self.editor.multi_cursor_manager.get_all_cursors()

        # Sort reverse for insertions (back to front) but track primary
        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None
        for cursor_state, original_index in sorted_with_index:
            if cursor_state == primary:
                primary_index = len(new_positions)

            qt_cursor.setPosition(cursor_state.anchor)
            qt_cursor.setPosition(cursor_state.position, QTextCursor.MoveMode.KeepAnchor)

            selected_text = qt_cursor.selectedText()
            if selected_text:
                # Wrap selection
                qt_cursor.insertText(open_char + selected_text + close_char)
                # Position cursor after opening char with selection
                new_pos = qt_cursor.position()
                new_anchor = new_pos - len(selected_text) - 1
                new_positions.append((new_anchor, new_pos - 1))
            else:
                # Insert pair and position between them
                qt_cursor.insertText(open_char + close_char)
                qt_cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
                new_pos = qt_cursor.position()
                new_positions.append((new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Reverse to get original order
        new_positions.reverse()

        # Adjust primary index and move to front
        if primary_index is not None:
            primary_index = len(new_positions) - 1 - primary_index
            if primary_index < len(new_positions):
                primary_cursor = new_positions.pop(primary_index)
                new_positions.insert(0, primary_cursor)

        # Update cursor positions
        from ..multi_cursor_manager import CursorState
        cursor_states = [CursorState(anchor, pos) for anchor, pos in new_positions]
        self.editor.multi_cursor_manager._set_all_cursors(cursor_states)

        return True
