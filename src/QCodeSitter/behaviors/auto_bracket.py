from __future__ import annotations
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore

from . import Behavior, HasKeyPress

if TYPE_CHECKING:
    from ..code_editor import CodeEditor

MM = QtGui.QTextCursor.MoveMode
MO = QtGui.QTextCursor.MoveOperation


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

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if not self.enabled:
            return

        if event.key() == QtCore.Qt.Key.Key_Backspace:
            self.delete_pair()
            return

        text = event.text()
        if len(text) != 1:
            return

        # Handle skipping over closing character
        skip_chars = set(self.pairs.values())
        if text in skip_chars:
            self.skip_closing(text)

        # Handle inserting opening character with its pair
        if text in self.pairs:
            self.insert_pair(text)

    def delete_pair(self):
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            if cursor.hasSelection():
                continue

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
                    pos = cursor.position()
                    cursor.setPosition(pos - 3)
                    cursor.setPosition(pos + 3, MM.KeepAnchor)
                    cursor.removeSelectedText()
                    citer.update_offset(-6)
                    citer.cursor_completed()

            # Check if we're between a pair
            elif col > 0 and col < len(text):
                before = text[col - 1]
                after = text[col]

                # Check if it's a matching pair
                if before in self.pairs and self.pairs[before] == after:
                    pos = cursor.position()
                    cursor.setPosition(pos - 1)
                    cursor.setPosition(pos + 1, MM.KeepAnchor)
                    cursor.removeSelectedText()
                    citer.update_offset(-2)
                    citer.cursor_completed()

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

    def _handle_triple_quote(
        self, cursor: QtGui.QTextCursor, quote: str, line: str, col: int
    ) -> tuple[bool, int]:
        """Handle triple-quote insertion and skipping for Python docstrings

        Returns:
            bool: If this was handled
            int: The character delta for this edit
        """
        # Check if we're about to skip over triple-quotes
        if col + 2 < len(line) and line[col : col + 3] == quote * 3:
            # Next three characters are the same quote - skip all three
            cursor.movePosition(MO.Right, MM.MoveAnchor, 3)
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
            cursor.movePosition(MO.Left, MM.MoveAnchor, 3)
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
                cursor.movePosition(MO.Left, MM.MoveAnchor, 3)
                cursor.endEditBlock()
                return True, 4

        # Not a triple-quote situation
        return False, 0

    def insert_pair(self, open_char: str):
        """Insert opening character and its closing pair

        Returns:
            bool: Whether this was handled
            int: The number of characters added/removed for this insertion
        """
        close_char = self.pairs[open_char]
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            # Check if there's a selection - if so, wrap it
            if cursor.hasSelection():
                selected_text = cursor.selectedText()

                cursor.insertText(open_char + selected_text + close_char)

                # Move cursor to after the opening character and keep the selection
                cursor.setPosition(cursor.position() - len(selected_text) - 1)
                cursor.movePosition(MO.Right, MM.KeepAnchor, len(selected_text))
                citer.update_offset(2)
                citer.cursor_completed()
                continue

            elif open_char in self._common:
                line = cursor.block().text()
                col = cursor.positionInBlock()

                if self._should_skip_triple_quote(open_char, line, col):
                    cursor.movePosition(MO.Right, MM.MoveAnchor, 3)
                    continue

                if self._should_skip_quote(open_char, line, col):
                    cursor.movePosition(MO.Right, MM.MoveAnchor, 1)
                    continue

                tc_handle, delta = self._handle_triple_quote(
                    cursor, open_char, line, col
                )
                if tc_handle:
                    citer.update_offset(delta)
                    citer.cursor_completed()
                    continue

            # Insert the pair
            cursor.insertText(open_char + close_char)
            cursor.movePosition(MO.Left, MM.MoveAnchor, 1)
            citer.update_offset(2)
            citer.cursor_completed()

    def skip_closing(self, open_char: str):
        """Skip over a closing character if it's already there"""

        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            cursor.movePosition(MO.Right, MM.KeepAnchor, 1)
            text = cursor.selectedText()
            if text == open_char:
                cursor.setPosition(cursor.position())
                citer.cursor_completed()
            else:
                cursor.movePosition(MO.Left, MM.MoveAnchor, 1)
