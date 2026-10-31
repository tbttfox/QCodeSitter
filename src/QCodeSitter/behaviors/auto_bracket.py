from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore, QtGui

from ..utils import len16
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor

MM = QtGui.QTextCursor.MoveMode
MO = QtGui.QTextCursor.MoveOperation


class AutoBracket(Behavior):
    """Automatically inserts closing brackets, quotes, and other paired characters"""

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.auto_bracket_enabled = True
        self.auto_bracket_pairs = "()[]{}\"\"''``"
        self.setListen({"auto_bracket_enabled", "auto_bracket_pairs"})
        # TODO: Add an option to enable/disable triple quotes
        self.updateAll()

    @property
    def auto_bracket_pairs(self) -> str:
        return self._pair_str

    @auto_bracket_pairs.setter
    def auto_bracket_pairs(self, pair_str: str):
        """Set the pairs from a string of opening and closing characters. ie: "()[]" """
        self._pair_str = pair_str
        # Map of opening characters to their closing pairs
        self.pairs = {pair_str[i]: pair_str[i + 1] for i in range(0, len(pair_str), 2)}
        self._closing = set(self.pairs.values())
        # Characters that open and close themselves, like quotes
        self._common = {k for k, v in self.pairs.items() if k == v}

    def hasKeyPress(self) -> bool:
        return True

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> bool:
        if not self.auto_bracket_enabled:
            return False

        if event.key() == QtCore.Qt.Key.Key_Backspace:
            self.delete_pair()
            return False

        text = event.text()
        if len(text) != 1:
            return False

        # Handle skipping over closing character
        if text in self._closing:
            self.skip_closing(text)

        # Handle inserting opening character with its pair
        if text in self.pairs:
            self.insert_pair(text)
        return False

    def delete_pair(self):
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            if cursor.hasSelection():
                continue

            block = cursor.block()
            text = block.text()
            col = min(cursor.positionInBlock(), len(text))

            # Check if we're between triple-quotes
            before_triple = text[col - 3 : col] if col >= 3 else ""
            if (
                before_triple
                and before_triple == text[col : col + 3]
                and before_triple in [i * 3 for i in self._common]
            ):
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

    def _insert_triple_quote(
        self, cursor: QtGui.QTextCursor, quote: str, line: str, col: int
    ) -> bool:
        """When typing the third quote of a docstring, insert the closing triple-quote

        Returns:
            bool: If this was handled
        """
        if col < 2 or line[col - 2 : col] != quote * 2:
            return False
        # Insert the opening third quote and three closing quotes
        cursor.insertText(quote * 4)
        cursor.movePosition(MO.Left, MM.MoveAnchor, 3)
        return True

    def insert_pair(self, open_char: str):
        """Insert opening character and its closing pair

        This runs after skip_closing, so any cursor right before a matching
        closing character has already been handled
        """
        close_char = self.pairs[open_char]
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            # Check if there's a selection - if so, wrap it
            if cursor.hasSelection():
                selected_text = cursor.selectedText()
                sel_len = len16(selected_text)
                cursor.insertText(open_char + selected_text + close_char)

                # Keep the selection, now inside the pair
                start = cursor.position() - sel_len - 1
                cursor.setPosition(start)
                cursor.setPosition(start + sel_len, MM.KeepAnchor)
                citer.update_offset(2)
                citer.cursor_completed()
                continue

            if open_char in self._common:
                line = cursor.block().text()
                col = min(cursor.positionInBlock(), len(line))
                if self._insert_triple_quote(cursor, open_char, line, col):
                    citer.update_offset(4)
                    citer.cursor_completed()
                    continue

            # Insert the pair
            cursor.insertText(open_char + close_char)
            cursor.movePosition(MO.Left, MM.MoveAnchor, 1)
            citer.update_offset(2)
            citer.cursor_completed()

    def skip_closing(self, close_char: str):
        """Skip over a closing character if it's already there"""
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            # Typing over a selection replaces or wraps it instead
            if cursor.hasSelection():
                continue
            cursor.movePosition(MO.Right, MM.KeepAnchor, 1)
            if cursor.selectedText() == close_char:
                cursor.setPosition(cursor.position())
                citer.cursor_completed()
            else:
                cursor.movePosition(MO.Left, MM.MoveAnchor, 1)
