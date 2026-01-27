from __future__ import annotations
from typing import TYPE_CHECKING

from Qt import QtGui, QtCore

from . import Behavior, HasHotkeys
from ..utils import len16
from QtShortcutManager import ShortcutSlot, ShortcutSlotGroup

if TYPE_CHECKING:
    from ..code_editor import CodeEditor

# Map tree-sitter language names to their line comment prefix
COMMENT_PREFIXES: dict[str, str] = {
    "python": "# ",
    "cpp": "// ",
    "c": "// ",
    "lua": "-- ",
    "bash": "# ",
}

MO = QtGui.QTextCursor.MoveOperation
MM = QtGui.QTextCursor.MoveMode


class CommentToggle(HasHotkeys, Behavior):
    """Toggle line comments for the current line or selection."""

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        lang = self.options["language"]
        self._comment_prefix = COMMENT_PREFIXES.get(lang.name, "# ")

    def getHotkeys(self) -> ShortcutSlotGroup:
        slots = [
            ShortcutSlot(
                name="Toggle Comment",
                defaults=[QtGui.QKeySequence("Ctrl+/")],
                desc="Toggle line comment on current line or selection",
            )
        ]
        return ShortcutSlotGroup("Comment", slots=slots)

    def toggle_comment(self):
        from ..code_editor import CursorIterator

        self.editor.tree_manager.pause()
        try:
            self.editor.citer = CursorIterator(self.editor)
            citer = self.editor.citer
            for cursor in citer.iterate_cursors():
                self._toggle_for_cursor(cursor, citer)
        finally:
            self.editor.tree_manager.unpause()

    def _toggle_for_cursor(self, cursor: QtGui.QTextCursor, citer):
        prefix = self._comment_prefix

        # Expand to full lines
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
        else:
            start = cursor.position()
            end = start

        cursor.setPosition(start)
        cursor.movePosition(MO.StartOfLine)
        cursor.setPosition(end, MM.KeepAnchor)
        cursor.movePosition(MO.EndOfLine, MM.KeepAnchor)

        start_pos = cursor.selectionStart()
        end_pos = cursor.selectionEnd()
        text = cursor.selection().toPlainText()
        lines = text.split("\n")

        # Determine direction: uncomment if ALL non-empty lines are commented
        should_uncomment = all(
            self._line_is_commented(line, prefix)
            for line in lines
            if line.strip()
        )

        if should_uncomment:
            new_lines = [self._uncomment_line(line, prefix) for line in lines]
        else:
            # Find minimum indentation of non-empty lines
            min_indent = self._min_indent(lines)
            new_lines = [self._comment_line(line, prefix, min_indent) for line in lines]

        ins = "\n".join(new_lines)
        old_size = end_pos - start_pos
        ins_size = len16(ins)
        cursor.insertText(ins)
        citer.update_offset(ins_size - old_size)

        # Restore selection
        cursor.setPosition(start_pos)
        cursor.setPosition(start_pos + ins_size, MM.KeepAnchor)
        citer.cursor_completed()

    @staticmethod
    def _line_is_commented(line: str, prefix: str) -> bool:
        stripped = line.lstrip()
        stripped_prefix = prefix.rstrip()
        return stripped.startswith(prefix) or stripped.startswith(stripped_prefix)

    @staticmethod
    def _min_indent(lines: list[str]) -> int:
        indents = []
        for line in lines:
            if line.strip():
                indents.append(len(line) - len(line.lstrip()))
        return min(indents) if indents else 0

    @staticmethod
    def _comment_line(line: str, prefix: str, min_indent: int) -> str:
        if not line.strip():
            return line
        return line[:min_indent] + prefix + line[min_indent:]

    @staticmethod
    def _uncomment_line(line: str, prefix: str) -> str:
        if not line.strip():
            return line
        indent = len(line) - len(line.lstrip())
        rest = line[indent:]
        if rest.startswith(prefix):
            return line[:indent] + rest[len(prefix):]
        # Handle prefix without trailing space (e.g. "#foo")
        stripped_prefix = prefix.rstrip()
        if rest.startswith(stripped_prefix):
            return line[:indent] + rest[len(stripped_prefix):]
        return line
