from __future__ import annotations
from . import HasKeyPress, Behavior
from ..utils import dedent_string, len16
from typing import TYPE_CHECKING
from Qt.QtWidgets import QAction
from Qt.QtGui import QFontMetrics, QTextCursor, QFont, QKeyEvent
from Qt.QtCore import Qt

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class SmartIndent(HasKeyPress, Behavior):
    def __init__(self, editor: CodeEditor):
        self.space_indent_width: int = 4
        self._tab_indent_width: int = 4
        self.indent_using_tabs: bool = False
        super().__init__(
            editor,
        )

        self.uiRetabAction = QAction("Retab", self.editor)
        self.uiRetabAction.triggered.connect(self.retab)

        self.setListen(
            {"space_indent_width", "tab_indent_width", "indent_using_tabs", "font"}
        )
        self.updateAll()

    def retab(self):
        # TODO
        pass

    @property
    def tab_indent_width(self) -> int:
        return self._tab_indent_width

    @tab_indent_width.setter
    def tab_indent_width(self, val: int):
        self._tab_indent_width = val
        metrics = QFontMetrics(self.editor.font())
        self.editor.setTabStopDistance(
            self.tab_indent_width * metrics.horizontalAdvance(" ")
        )

    def _font(self, _val: QFont):
        metrics = QFontMetrics(self.editor.font())
        self.editor.setTabStopDistance(
            self.tab_indent_width * metrics.horizontalAdvance(" ")
        )

    font = property(None, _font)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.smartNewline()
        elif event.key() == Qt.Key.Key_Tab:
            self.insertIndent()
        elif event.key() == Qt.Key.Key_Backtab:
            self.unindent()
        elif event.key() == Qt.Key.Key_Return:
            self.smartNewline()
        elif event.key() == Qt.Key.Key_Backspace:
            self.smartBackspace()
        else:
            text = event.text()
            if text in ("]", ")", "}"):
                self.smartClosingBracket(text)

    def expandCursorToLines(self, cursor: QTextCursor):
        """Expand a cursor selection to whole lines
        If there is no selection, expand to the current line
        """
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
        else:
            start = cursor.position()
            end = start

        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)

    def _get_newline_indent(self, cursor: QTextCursor) -> str:
        """Calculate the indentation string to insert after a newline.

        This is a pure calculation function with no side effects - it just determines
        what indent string should be inserted based on the syntax and cursor position.

        Args:
            line_num: The line number (0-indexed)
            col: The column position in the line
            line_text: The text of the current line
            indent: The current indentation of the line

        Returns:
            The complete indentation string to insert (may include extra indent or dedent)
        """
        # Get current line text and indentation
        block = cursor.block()
        line_text = block.text()
        stripped = line_text.lstrip()
        indent = line_text[: len(line_text) - len(stripped)]

        # Get cursor position
        line_num = block.blockNumber()
        col = cursor.positionInBlock()

        stripped = line_text.lstrip()

        # Special case: if the current line is empty/whitespace-only, just copy the indentation
        if stripped == "":
            return indent

        # Special case: if cursor is at the beginning of the line
        if col == 0:
            # Use previous line's indentation if available
            prev_block = block.previous()
            if prev_block.isValid():
                prev_text = prev_block.text()
                prev_stripped = prev_text.lstrip()
                return prev_text[: len(prev_text) - len(prev_stripped)]
            else:
                return ""

        # Look at the position just before the cursor to find the statement we just finished
        lookup_col = max(0, col - 1) if col > 0 else 0

        # Determine indent action based on syntax analysis
        extra_indent = ""
        dedent = False

        # Check if we should add indent (opening block)
        saz = self.editor.syntax_analyzer

        if saz.should_indent_after_position(line_num, lookup_col):
            if self.indent_using_tabs:
                extra_indent = "\t"
            else:
                extra_indent = " " * self.space_indent_width

        # Check if we should dedent (closing block or return statement)
        elif saz.should_dedent_after_position(line_num, lookup_col, line_text):
            dedent = True

        # Apply dedent if needed
        final_indent = indent
        if dedent:
            final_indent = dedent_string(
                indent, self.indent_using_tabs, self.space_indent_width
            )

        return final_indent + extra_indent

    def smartNewline(self):
        """Insert a newline with smart indentation based on tree-sitter parse tree"""
        citer = self.editor.citer
        for cursor, _is_primary in citer.iterate_cursors():
            if cursor.hasSelection():
                citer.update_offset(cursor.selectionStart() - cursor.selectionEnd())
                cursor.removeSelectedText()
            indent_str = self._get_newline_indent(cursor)
            cursor.insertText("\n" + indent_str)
            citer.update_offset(len16(indent_str) + 1)
            citer.cursor_completed()

    def insertIndent(self):
        """Indent at the given cursor, either a single line or all the lines in a selection"""
        citer = self.editor.citer
        for cursor, _is_primary in citer.iterate_cursors():
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
                citer.update_offset(len16(indent))
                citer.cursor_completed()
                continue
            else:
                self.expandCursorToLines(cursor)
                start_pos = cursor.selectionStart()
                end_pos = cursor.selectionEnd()
                text = cursor.selection().toPlainText()
                lines = text.split("\n")
                if self.indent_using_tabs:
                    indent = "\t"
                else:
                    indent = " " * self.space_indent_width
                lines = [
                    indent + line if line.strip() != "" else line for line in lines
                ]
                ins = "\n".join(lines)
                old_size = end_pos - start_pos
                ins_size = len16(ins)
                cursor.insertText(ins)
                citer.update_offset(ins_size - old_size)

                # Restore selection, adjusting for the added indent
                cursor.setPosition(start_pos)
                cursor.setPosition(start_pos + ins_size, QTextCursor.KeepAnchor)
                citer.cursor_completed()

    def unindent(self):
        """Unindent the given cursor, either a single line or all the lines in a selection"""
        citer = self.editor.citer
        for cursor, _is_primary in citer.iterate_cursors():
            self.expandCursorToLines(cursor)
            start_pos = cursor.selectionStart()
            end_pos = cursor.selectionEnd()
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
            ins = "\n".join(newlines)
            ins_size = len16(ins)
            old_size = end_pos - start_pos
            cursor.insertText(ins)
            citer.update_offset(ins_size - old_size)

            # Restore selection, adjusting for the removed indent
            cursor.setPosition(start_pos)
            cursor.setPosition(start_pos + ins_size, QTextCursor.KeepAnchor)
            citer.cursor_completed()

    def smartBackspace(self):
        """If backspacing at an the end of indentation, remove an entire "tab" of
        spaces. Otherwise just do a regular backspace
        """
        if self.indent_using_tabs:
            return
        citer = self.editor.citer
        for cursor, _is_primary in citer.iterate_cursors():
            if cursor.hasSelection():
                continue
            col = cursor.positionInBlock()
            if col == 0:
                continue

            # Check if all preceding characters are spaces
            # This is only dealing with whitespace, so we don't have to worry about encoding
            text = cursor.block().text()
            lset = set(text[:col])
            if len(lset) != 1:
                continue
            if lset.pop() != " ":
                continue

            # Delete up to the tabstop
            delete = col % self.space_indent_width
            if delete == 0:
                delete = self.space_indent_width
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, delete)
            cursor.removeSelectedText()
            citer.update_offset(-delete)
            citer.cursor_completed()

    def smartClosingBracket(self, bracket):
        """Auto-dedent when typing a closing bracket if the line only contains whitespace

        Args:
            cursor: The text cursor
            bracket: The closing bracket character (']', ')', or '}')
        """
        citer = self.editor.citer
        for cursor, _is_primary in citer.iterate_cursors():
            if cursor.hasSelection():
                citer.update_offset(cursor.selectionStart() - cursor.selectionEnd())
                cursor.removeSelectedText()

            block = cursor.block()
            line_text = block.text()
            col = cursor.positionInBlock()

            # Check if everything before the cursor is whitespace
            before_cursor = line_text[:col]
            if before_cursor.strip() != "":
                continue

            # Check if everything after the cursor is whitespace
            after_cursor = line_text[col:]
            if after_cursor.strip() != "":
                continue

            # The line is all whitespace, so we should dedent before inserting the bracket
            stripped = line_text.lstrip()
            indent = line_text[: len(line_text) - len(stripped)]

            if len(indent) == 0:
                continue

            # Remove the current line's indentation and replace with dedented version + bracket
            dedented_indent = dedent_string(
                indent, self.indent_using_tabs, self.space_indent_width
            )

            # Replace the entire line with dedented indent + bracket
            cursor.movePosition(QTextCursor.StartOfLine)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)

            oldlen = cursor.selectionEnd() - cursor.selectionStart()
            newtxt = dedented_indent + bracket
            newlen = len16(newtxt)
            cursor.insertText(dedented_indent + bracket)

            citer.update_offset(newlen - oldlen)
            citer.cursor_completed()
