from __future__ import annotations

import re
from typing import TYPE_CHECKING

from Qt import QtGui

from ..tracked_document import len16, utf16_to_index
from ..utils import KEY, MM, MO, MOD
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor

# Python string prefixes, which still get a pair of quotes when typed before one
_STRING_PREFIXES = frozenset({"r", "u", "b", "f", "br", "rb", "fr", "rf"})


class AutoBracket(Behavior):
    """Automatically inserts closing brackets, quotes, and other paired characters

    The pairs come from the "auto_bracket_pairs" option
    """

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.watch_options({"auto_bracket_pairs": self._set_pairs})

    def _set_pairs(self, pairs: list[str]) -> None:
        """Set the pairs from strings of an opening and closing character, ie "()" """
        self.pairs = {pair[0]: pair[1] for pair in pairs}
        self._closing = set(self.pairs.values())
        # Characters that open and close themselves, like quotes
        self._self_closing = {k for k, v in self.pairs.items() if k == v}

    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        """Handle the cursors next to pairs, and leave the rest to the editor"""
        text = event.text()
        if event.key() == KEY.Key_Backspace:
            if event.modifiers() & MOD.ControlModifier:
                # Ctrl+Backspace deletes a word, which EditingKeys does
                return False
            self._delete_pair()
        elif text in self._closing or text in self.pairs:
            if text in self._closing:
                self._skip_closing(text)
            if text in self.pairs:
                self._insert_pair(text)
        else:
            return False
        return self.editor.citer.all_completed()

    def _pair_around(self, text: str, index: int) -> str | None:
        """Get the empty pair, or pair of triple quotes, that a str index is inside"""
        before = text[max(0, index - 3) : index]
        quote = before[:1]
        if len(before) == 3 and quote in self._self_closing and before == quote * 3:
            if text[index : index + 3] == before:
                return before * 2
        if 0 < index < len(text) and self.pairs.get(text[index - 1]) == text[index]:
            return text[index - 1 : index + 1]
        return None

    def _delete_pair(self) -> None:
        """Backspace both halves of an empty pair"""
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            if cursor.hasSelection():
                continue
            text = cursor.block().text()
            pair = self._pair_around(
                text, utf16_to_index(text, cursor.positionInBlock())
            )
            if pair is None:
                continue
            half = len16(pair) // 2
            pos = cursor.position()
            cursor.setPosition(pos - half)
            cursor.setPosition(pos + half, MM.KeepAnchor)
            cursor.removeSelectedText()
            citer.mark_cursor_completed()

    def _insert_pair(self, open_char: str) -> None:
        """Insert an opening character and its closing pair

        This runs after _skip_closing, so any cursor right before a matching
        closing character has already been handled
        """
        close_char = self.pairs[open_char]
        citer = self.editor.citer
        for cursor in citer.iterate_cursors(complete_all=True):
            if cursor.hasSelection():
                # Wrap the selection, and keep it selected inside the pair
                selected_text = cursor.selectedText()
                start = cursor.selectionStart() + len16(open_char)
                cursor.insertText(open_char + selected_text + close_char)
                cursor.setPosition(start)
                cursor.setPosition(start + len16(selected_text), MM.KeepAnchor)
            elif open_char in self._self_closing and self._typing_triple_quote(
                cursor, open_char
            ):
                # Close the docstring, with the cursor inside it
                cursor.insertText(open_char * 4)
                cursor.movePosition(MO.Left, MM.MoveAnchor, 3)
            elif open_char == "'" and self._after_word(cursor):
                # An apostrophe inside a word, like don't
                cursor.insertText(open_char)
            else:
                cursor.insertText(open_char + close_char)
                cursor.movePosition(MO.Left, MM.MoveAnchor, 1)

    @staticmethod
    def _typing_triple_quote(cursor: QtGui.QTextCursor, quote: str) -> bool:
        """Whether typing this quote makes three in a row"""
        text = cursor.block().text()
        index = utf16_to_index(text, cursor.positionInBlock())
        return index >= 2 and text[index - 2 : index] == quote * 2

    @staticmethod
    def _after_word(cursor: QtGui.QTextCursor) -> bool:
        """Whether the cursor follows a word that is not a string prefix"""
        text = cursor.block().text()
        index = utf16_to_index(text, cursor.positionInBlock())
        match = re.search(r"\w*$", text[:index])
        word = match.group() if match else ""
        return bool(word) and word.lower() not in _STRING_PREFIXES

    def _skip_closing(self, close_char: str) -> None:
        """Step over a closing character instead of typing a second one"""
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            # Typing over a selection replaces or wraps it instead
            if cursor.hasSelection():
                continue
            cursor.movePosition(MO.Right, MM.KeepAnchor, 1)
            if cursor.selectedText() == close_char:
                cursor.setPosition(cursor.position())
                citer.mark_cursor_completed()
            else:
                # Go back to where it started. At the end of the document it never moved
                cursor.setPosition(cursor.anchor())
