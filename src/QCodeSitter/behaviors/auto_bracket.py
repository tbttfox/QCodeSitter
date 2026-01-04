from __future__ import annotations
from Qt.QtGui import QKeyEvent, QTextCursor
from Qt.QtCore import Qt
from typing import TYPE_CHECKING
from . import Behavior, HasKeyPress
from ..multi_cursor_manager import CursorState

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


def _build_pair_from_str(pair_str):
    pairs = {pair_str[i]: pair_str[i + 1] for i in range(0, len(pair_str), 2)}
    common = set(k for k, v in pairs.items() if k == v)
    return pairs, common


class AutoBracket(HasKeyPress, Behavior):
    """Automatically inserts closing brackets, quotes, and other paired characters"""

    # Map of opening characters to their closing pairs
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.enabled = True
        self._pairs, self._common = _build_pair_from_str("()[]{}\"\"''``")
        self.setListen({"auto_bracket_enabled", "auto_bracket_pairs"})
        # TODO: Add an option to enable/disable triple quotes
        self.updateAll()

    @property
    def pairs(self):
        return self._pairs

    @pairs.setter
    def pairs(self, pair_str):
        self._pairs, self._common = _build_pair_from_str(pair_str)

    def updateOptions(self, keys):
        super().updateOptions(keys)
        if "auto_bracket_enabled" in keys:
            self.enabled = self.options.get("auto_bracket_enabled", True)

    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        if not self.enabled:
            return False

        text = event.text()

        # Handle character insertion (opening or closing brackets/quotes)
        if text and len(text) == 1:
            # Handle inserting opening character with its pair
            if text in self.pairs:
                return self.insert_pair(text)

            # Handle skipping over closing character
            skip_chars = set(self.pairs.values())
            if text in skip_chars:
                return self.skip_closing(text)

        if event.key() == Qt.Key_Backspace:
            return self.delete_pair()

        return False

    def insert_pair(self, open_char: str) -> bool:
        if not self.editor.cursor.is_multi_mode:
            cursor = self.editor.textCursor()
            handled, _delta = self._insert_pair(cursor, open_char)
            if handled:
                self.editor.setTextCursor(cursor)
            return handled
        return self._insert_pair_multi_cursor(open_char)

    def skip_closing(self, open_char: str) -> bool:
        if not self.editor.cursor.is_multi_mode:
            cursor = self.editor.textCursor()
            ret = self._skip_closing(cursor, open_char)
            if ret:
                self.editor.setTextCursor(cursor)
            return ret
        return self._skip_closing_multi_cursor(open_char)

    def delete_pair(self) -> bool:
        if not self.editor.cursor.is_multi_mode:
            cursor = self.editor.textCursor()
            ret = self._delete_pair(cursor)
            if ret:
                cursor = self.editor.textCursor()
            return ret
        return self._delete_pair_multi_cursor()

    def _insert_pair(self, cursor: QTextCursor, open_char: str) -> tuple[bool, int]:
        """Insert opening character and its closing pair

        Returns:
            bool: Whether this was handled
            int: The number of characters added/removed for this insertion
        """
        close_char = self.pairs[open_char]

        # Check if there's a selection - if so, wrap it
        if cursor.hasSelection():
            selected_text = cursor.selectedText()

            cursor.beginEditBlock()
            cursor.insertText(open_char + selected_text + close_char)
            cursor.endEditBlock()

            # Move cursor to after the opening character and keep the selection
            cursor.setPosition(cursor.position() - len(selected_text) - 1)
            cursor.movePosition(
                QTextCursor.Right, QTextCursor.KeepAnchor, len(selected_text)
            )
            return True, 2

        if open_char in self._common:
            line = cursor.block().text()
            col = cursor.positionInBlock()

            if self._should_skip_triple_quote(open_char, line, col):
                cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 3)
                return True, 0

            if self._should_skip_quote(open_char, line, col):
                cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 1)
                return True, 0

            tc_handle, delta = self._handle_triple_quote(cursor, open_char, line, col)
            if tc_handle:
                return True, delta

        # Insert the pair
        cursor.beginEditBlock()
        cursor.insertText(open_char + close_char)
        cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 1)
        cursor.endEditBlock()
        return True, 2

    def _insert_pair_multi_cursor(self, open_char: str) -> bool:
        """Insert opening character and its closing pair at all cursors"""
        # Get primary cursor before sorting
        sorted_cursors, primary_index = (
            self.editor.multi_cursor_manager.get_all_cursors()
        )
        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        curr_offset = 0
        for cursor_state in sorted_cursors:
            cursor_state.offset(curr_offset)
            cursor_state.apply(qt_cursor)

            _handled, delta = self._insert_pair(qt_cursor, open_char)
            curr_offset += delta

        qt_cursor.endEditBlock()

        primary = sorted_cursors.pop(primary_index)
        sorted_cursors.insert(0, primary)

        self.editor.multi_cursor_manager._set_all_cursors(sorted_cursors)
        return True

    def _handle_triple_quote(
        self, cursor: QTextCursor, quote: str, line: str, col: int
    ) -> tuple[bool, int]:
        """Handle triple-quote insertion and skipping for Python docstrings

        Returns:
            bool: If this was handled
            int: The character delta for this edit
        """
        # Check if we're about to skip over triple-quotes
        if col + 2 < len(line) and line[col : col + 3] == quote * 3:
            # Next three characters are the same quote - skip all three
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 3)
            return True, 0

        # Check if we already have two quotes before cursor
        # Two cases:
        # 1. User typed two quotes manually: line[col-2:col] == quote*2
        # 2. User typed one quote, auto-pair inserted second: line[col-1] == quote and line[col] == quote
        before_two = col >= 2 and line[col - 2 : col] == quote * 2
        before_one_after_one = (
            col >= 1
            and col < len(line)
            and line[col - 1] == quote
            and line[col] == quote
        )

        if before_two and not before_one_after_one:
            # Case 1: User typed two quotes, now typing third
            # Insert the opening third quote and three closing quotes
            cursor.beginEditBlock()
            cursor.insertText(quote + quote * 3)
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 3)
            cursor.endEditBlock()
            return True, 4

        elif before_one_after_one:
            # Case 2: User typed one quote (auto-paired to two), now typing second
            # Check if there's another quote before the auto-paired quotes
            if col >= 2 and line[col - 2] == quote:
                # We have: qq|q (where | is cursor, q is quote)
                # User is typing the third quote
                # Delete the auto-paired closing quote and insert triple-quote pair
                cursor.beginEditBlock()
                cursor.deleteChar()  # Remove the auto-paired quote
                cursor.insertText(
                    quote + quote * 3
                )  # Add opening third + closing three
                cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 3)
                cursor.endEditBlock()
                return True, 4

        # Not a triple-quote situation
        return False, 0

    def _should_skip_quote(self, quote: str, line: str, col: int) -> bool:
        """Determine if we should skip over a quote instead of inserting a pair"""
        # If next character is the same quote, skip over it
        if col < len(line) and line[col] == quote:
            return True

        return False

    def _should_skip_triple_quote(self, quote: str, line: str, col: int) -> bool:
        """Handle triple-quote insertion and skipping for Python docstrings

        Returns:
            True if triple-quote was handled (inserted or skipped)
            False if we should fall through to normal quote handling
            None if we shouldn't handle this event at all
        """
        # Check if we're about to skip over triple-quotes
        if col + 2 < len(line) and line[col : col + 3] == quote * 3:
            return True
        return False

    def _skip_closing(self, cursor: QTextCursor, char: str) -> bool:
        """Skip over a closing character if it's already there"""
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()

        # Check if the character after cursor matches
        if col < len(text) and text[col] == char:
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 1)
            return True

        return False

    def _skip_closing_multi_cursor(self, char: str) -> bool:
        """Skip over a closing character if it's already there at all cursors"""

        all_cursors, _primary_index = self.editor.multi_cursor_manager.get_all_cursors()

        # Check if ALL cursors have the closing character after them
        # If any cursor doesn't, we should insert instead of skip
        doc = self.editor.document()
        for cursor_state in all_cursors:
            if cursor_state.has_selection:
                # If there's a selection, don't skip (would be wrapping)
                return False

            block = doc.findBlock(cursor_state.position)
            if not block.isValid():
                return False

            text = block.text()
            col = cursor_state.position - block.position()

            # Check if the character after cursor matches
            if col >= len(text) or text[col] != char:
                # This cursor doesn't have the closing char to skip
                return False

        # All cursors have the closing character - skip over it at all positions
        new_cursors = []
        for cursor_state in all_cursors:
            new_pos = cursor_state.position + 1
            new_cursors.append(CursorState(new_pos, new_pos))

        self.editor.multi_cursor_manager._set_all_cursors(new_cursors)
        return True

    def _delete_pair(self, cursor: QTextCursor) -> bool:
        """Delete both characters of a pair when backspacing"""
        if cursor.hasSelection():
            return False

        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()

        # Check for triple-quote deletion
        if col >= 3 and col + 3 <= len(text):
            trips = [i * 3 for i in self._common]
            before_triple = text[col - 3 : col]
            after_triple = text[col : col + 3]
            # Check if we're between triple-quotes
            if before_triple in trips and before_triple == after_triple:
                cursor.beginEditBlock()
                # Delete the three before
                for _ in range(3):
                    cursor.deletePreviousChar()
                # Delete the three after
                for _ in range(3):
                    cursor.deleteChar()
                cursor.endEditBlock()
                return True

        # Check if we're between a pair
        if col > 0 and col < len(text):
            before = text[col - 1]
            after = text[col]

            # Check if it's a matching pair
            if before in self.pairs and self.pairs[before] == after:
                cursor.beginEditBlock()
                cursor.deletePreviousChar()  # Delete opening char
                cursor.deleteChar()  # Delete closing char
                cursor.endEditBlock()
                return True

        return False

    def _delete_pair_multi_cursor(self):
        return False


class AutoBracket2(HasKeyPress, Behavior):
    """Automatically inserts closing brackets, quotes, and other paired characters"""

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.enabled = True
        self._pairs, self._common = _build_pair_from_str("()[]{}\"\"''``")
        self.setListen({"auto_bracket_enabled", "auto_bracket_pairs"})
        self.updateAll()

    @property
    def pairs(self):
        return self._pairs

    @pairs.setter
    def pairs(self, pair_str):
        self._pairs, self._common = _build_pair_from_str(pair_str)

    def updateOptions(self, keys):
        super().updateOptions(keys)
        if "auto_bracket_enabled" in keys:
            self.enabled = self.options.get("auto_bracket_enabled", True)

    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        if not self.enabled:
            return False

        text = event.text()

        # Handle character insertion (opening or closing brackets/quotes)
        if text and len(text) == 1:
            all_cursors, _primary_index = self.editor.multi_cursor_manager.get_all_cursors()
            primary_cursor = all_cursors[_primary_index]
            for cursor_state in all_cursors:
                self.insert_pair(cursor_state, text)

                # Handle skipping over closing character
                skip_chars = set(self.pairs.values())
                if text in skip_chars:
                    return self.skip_closing(text)

        if event.key() == Qt.Key_Backspace:
            return self.delete_pair()

        return False





    def insert_pair(self, open_char: str) -> bool:

        all_cursors, _primary_index = self.editor.multi_cursor_manager.get_all_cursors()
        primary_cursor = all_cursors[_primary_index]




        # Check if ALL cursors have the closing character after them
        # If any cursor doesn't, we should insert instead of skip
        doc = self.editor.document()
        for cursor_state in all_cursors:
            if cursor_state.has_selection:








