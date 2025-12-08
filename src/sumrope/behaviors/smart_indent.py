from __future__ import annotations
from . import HasKeyPress, Behavior
from ..utils import hk, dedent_string
from typing import TYPE_CHECKING, Callable
from Qt.QtGui import QFontMetrics, QTextCursor, QFont, QKeyEvent
from Qt.QtCore import Qt

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


class SmartIndent(HasKeyPress, Behavior):
    def __init__(self, editor: CodeEditor):
        self.space_indent_width: int = 4
        self._tab_indent_width: int = 4
        self.indent_using_tabs: bool = False
        super().__init__(
            editor,
        )

        self.setListen(
            {"space_indent_width", "tab_indent_width", "indent_using_tabs", "font"}
        )
        self.hotkeys: dict[str, Callable[[QTextCursor], bool]] = {
            hk(Qt.Key.Key_Tab): self.insertIndent,
            hk(Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier): self.unindent,
            hk(Qt.Key.Key_Return): self.smartNewline,
            hk(Qt.Key.Key_Backspace): self.smartBackspace,
        }
        self.updateAll()

    @property
    def tab_indent_width(self) -> int:
        return self._tab_indent_width

    @tab_indent_width.setter
    def tab_indent_width(self, val: int):
        self._tab_indent_width = val
        metrics = QFontMetrics(self.editor.font())
        self.editor.setTabStopWidth(self.tab_indent_width * metrics.width(" "))

    def _font(self, _val: QFont):
        metrics = QFontMetrics(self.editor.font())
        self.editor.setTabStopWidth(self.tab_indent_width * metrics.width(" "))

    font = property(None, _font)

    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        # Check for closing brackets that should trigger auto-dedent
        func = self.hotkeys.get(hotkey)
        if func is not None:
            cursor = self.editor.textCursor()
            if func(cursor):
                self.editor.setTextCursor(cursor)
                return True

        text = event.text()
        if text in ("]", ")", "}"):
            cursor = self.editor.textCursor()
            if self.smartClosingBracket(cursor, text):
                self.editor.setTextCursor(cursor)
                return True
        return False

    def smartNewline(self, cursor: QTextCursor) -> bool:
        """Insert a newline with smart indentation based on tree-sitter parse tree"""
        if self.editor is None:
            return False
        # Get current line text and indentation
        block = cursor.block()
        line_text = block.text()
        stripped = line_text.lstrip()
        indent = line_text[: len(line_text) - len(stripped)]

        # Get cursor position
        line_num = block.blockNumber()
        col = cursor.positionInBlock()

        # Special case: if the current line is empty/whitespace-only, just copy the indentation
        # Don't do syntax analysis on empty lines
        # Check this BEFORE the col==0 check so empty lines maintain their indentation
        if stripped == "":
            cursor.insertText("\n" + indent)
            return True

        # Special case: if cursor is at the beginning of the line, just insert a blank line
        # with the indentation from the previous line (if any)
        if col == 0:
            prev_block = block.previous()
            if prev_block.isValid():
                prev_text = prev_block.text()
                prev_stripped = prev_text.lstrip()
                prev_indent = prev_text[: len(prev_text) - len(prev_stripped)]
                cursor.insertText("\n" + prev_indent)
            else:
                cursor.insertText("\n")
            return True

        # Look at the position just before the cursor to find the statement we just finished
        # This handles the case where cursor is after a colon with no content yet
        lookup_col = max(0, col - 1) if col > 0 else 0

        # Determine indent action based on syntax analysis
        extra_indent = ""
        dedent = False

        # Check if we should add indent (opening block)
        should_indent = self.editor.syntax_analyzer.should_indent_after_position(
            line_num, lookup_col
        )

        if should_indent:
            if self.indent_using_tabs:
                extra_indent = "\t"
            else:
                extra_indent = " " * self.space_indent_width

        # Check if we should dedent (closing block or return statement)
        elif self.editor.syntax_analyzer.should_dedent_after_position(
            line_num, lookup_col, line_text
        ):
            dedent = True

        # Apply dedent if needed
        final_indent = indent
        if dedent:
            final_indent = dedent_string(
                indent, self.indent_using_tabs, self.space_indent_width
            )

        # Insert newline and indentation
        cursor.insertText("\n" + final_indent + extra_indent)
        return True

    def smartClosingBracket(self, cursor: QTextCursor, bracket: str) -> bool:
        """Auto-dedent when typing a closing bracket if the line only contains whitespace

        Args:
            cursor: The text cursor
            bracket: The closing bracket character (']', ')', or '}')

        Returns:
            True if we handled the bracket insertion, False to use default behavior
        """
        # Only auto-dedent if we're at the end of a line that contains only whitespace
        block = cursor.block()
        line_text = block.text()
        col = cursor.positionInBlock()

        # Check if everything before the cursor is whitespace
        before_cursor = line_text[:col]
        if before_cursor.strip() != "":
            return False  # There's non-whitespace content, use normal behavior

        # Check if everything after the cursor is whitespace
        after_cursor = line_text[col:]
        if after_cursor.strip() != "":
            return False  # There's non-whitespace content after cursor

        # The line is all whitespace, so we should dedent before inserting the bracket
        stripped = line_text.lstrip()
        indent = line_text[: len(line_text) - len(stripped)]

        if len(indent) == 0:
            return False  # No indentation to remove

        # Remove the current line's indentation and replace with dedented version + bracket
        dedented_indent = dedent_string(
            indent, self.indent_using_tabs, self.space_indent_width
        )

        # Replace the entire line with dedented indent + bracket
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        cursor.insertText(dedented_indent + bracket)

        return True

    def smartBackspace(self, cursor: QTextCursor) -> bool:
        """If backspacing at an the end of indentation, remove an entire "tab" of
        spaces. Otherwise just do a regular backspace
        """
        if self.indent_using_tabs:
            return False

        if cursor.hasSelection():
            return False
        col = cursor.positionInBlock()
        if col == 0:
            return False  # normal backspace

        # Check if all preceding characters are spaces
        text = cursor.block().text()
        lset = set(text[:col])
        if len(lset) != 1:
            return False  # normal backspace
        if lset.pop() != " ":
            return False  # normal backspace

        # If we are not aligned to the indent width, delete 1 space
        delete = 1 if (col % self.space_indent_width) != 0 else self.space_indent_width

        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, delete)
        cursor.removeSelectedText()
        return True

    def tabsToSpaces(self):
        """Convert leading tabs to spaces"""
        newlines = []
        for line in self.editor.document().iter_line_range():
            stripped = line.lstrip("\t")
            tabcount = len(line) - len(stripped)
            if tabcount:
                line = " " * (self.space_indent_width * tabcount) + stripped
            newlines.append(line)
        self.editor.updateAllLines("".join(newlines))

    def spacesToTabs(self):
        """Convert leading groups of spaces to tabs"""
        newlines = []
        for line in self.editor.document().iter_line_range():
            stripped = line.lstrip(" ")
            spacecount = len(line) - len(stripped)
            tabcount = spacecount // self.space_indent_width
            spacecount = spacecount - (tabcount * self.space_indent_width)
            if tabcount:
                line = ("\t" * tabcount) + (" " * spacecount) + stripped
            newlines.append(line)
        self.editor.updateAllLines("".join(newlines))

    def insertIndent(self, cursor: QTextCursor) -> bool:
        """Indent at the given cursor, either a single line or all the lines in a selection"""
        if not cursor.hasSelection():
            if self.indent_using_tabs:
                indent = "\t"
            else:
                pos = cursor.positionInBlock()
                indentCount = pos % self.space_indent_width
                if indentCount == 0:
                    indentCount = self.space_indent_width
                indent = " " * indentCount
            cursor.insertText(indent)
            return True

        self.editor.expandCursorToLines(cursor)
        text = cursor.selection().toPlainText()
        lines = text.split("\n")
        if self.indent_using_tabs:
            indent = "\t"
        else:
            indent = " " * self.space_indent_width
        lines = [indent + line if line.strip() != "" else line for line in lines]
        cursor.insertText("\n".join(lines))
        return True

    def unindent(self, cursor: QTextCursor) -> bool:
        """Unindent the given cursor, either a single line or all the lines in a selection"""
        self.editor.expandCursorToLines(cursor)
        text = cursor.selection().toPlainText()
        lines = text.split("\n")
        if self.indent_using_tabs:
            newlines = [line[1:] if line[0] == "\t" else line for line in lines]
        else:
            newlines = [
                line[: self.space_indent_width].lstrip(" ")
                + line[self.space_indent_width :]
                for line in lines
            ]
        cursor.insertText("\n".join(newlines))
        return True

