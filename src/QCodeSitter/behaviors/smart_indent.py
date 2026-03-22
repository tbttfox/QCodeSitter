from __future__ import annotations
from typing import TYPE_CHECKING

from Qt import QtWidgets, QtGui, QtCore


from . import HasKeyPress, Behavior
from ..utils import dedent_string, len16

if TYPE_CHECKING:
    from ..code_editor import CodeEditor

MO = QtGui.QTextCursor.MoveOperation
MM = QtGui.QTextCursor.MoveMode


class SmartIndent(Behavior):
    def __init__(self, editor: CodeEditor):
        self.space_indent_width: int = 4
        self._tab_indent_width: int = 4
        self.indent_using_tabs: bool = False
        self.indent_bracket_pairs: list[str] = ["()", "{}", "[]"]

        super().__init__(
            editor,
        )

        self.uiRetabAction = QtWidgets.QAction("Retab", self.editor)
        self.uiRetabAction.triggered.connect(self.retab)

        self.setListen(
            {
                "space_indent_width",
                "tab_indent_width",
                "indent_using_tabs",
                "indent_bracket_pairs",
                "font",
            }
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
        metrics = QtGui.QFontMetrics(self.editor.font())
        self.editor.setTabStopDistance(
            self.tab_indent_width * metrics.horizontalAdvance(" ")
        )

    def _font(self, _val: QtGui.QFont):
        metrics = QtGui.QFontMetrics(self.editor.font())
        self.editor.setTabStopDistance(
            self.tab_indent_width * metrics.horizontalAdvance(" ")
        )

    font = property(None, _font)

    def hasKeyPress(self) -> bool:
        return True

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> bool:
        if event.key() == QtCore.Qt.Key.Key_Return:
            self.smartNewline()
        elif event.key() == QtCore.Qt.Key.Key_Tab:
            self.insertIndent()
            return True
        elif event.key() == QtCore.Qt.Key.Key_Backtab:
            self.unindent()
            return True
        elif event.key() == QtCore.Qt.Key.Key_Backspace:
            self.smartBackspace()
        else:
            text = event.text()
            if text in ("]", ")", "}"):
                self.smartClosingBracket(text)
        return False

    def expandCursorToLines(self, cursor: QtGui.QTextCursor):
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
        cursor.movePosition(MO.StartOfLine)
        cursor.setPosition(end, MM.KeepAnchor)
        cursor.movePosition(MO.EndOfLine, MM.KeepAnchor)

    def _get_one_indent(self):
        if self.indent_using_tabs:
            return "\t"
        return " " * self.space_indent_width

    def _get_newline_indent(self, cursor: QtGui.QTextCursor) -> tuple[str, int]:
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
            return indent, 0

        # Special case: if cursor is at the beginning of the line
        if col == 0:
            # Use previous line's indentation if available
            prev_block = block.previous()
            if prev_block.isValid():
                prev_text = prev_block.text()
                prev_stripped = prev_text.lstrip()
                return prev_text[: len(prev_text) - len(prev_stripped)], 0
            else:
                return "", 0

        # Special case: If the cursor is between two brackets
        # self.indent_bracket_pairs: str = "(){}[]"
        tmp = QtGui.QTextCursor(cursor)
        tmp.movePosition(MO.Left, MM.MoveAnchor, 1)
        tmp.movePosition(MO.Right, MM.KeepAnchor, 2)
        wrap = tmp.selectedText()
        if wrap in self.indent_bracket_pairs:
            extra_indent = self._get_one_indent()
            return indent + extra_indent + "\n" + indent, -(len(indent) + 1)

        # Look at the position just before the cursor to find the statement we just finished
        lookup_col = max(0, col - 1) if col > 0 else 0

        # Determine indent action based on syntax analysis
        saz = self.editor.syntax_analyzer

        # Check if we should add indent (opening block)
        extra_indent = ""
        dedent = False
        if saz.should_indent_after_position(line_num, lookup_col):
            extra_indent = self._get_one_indent()

        # Check if we should dedent (closing block or return statement)
        elif saz.should_dedent_after_position(line_num, lookup_col, line_text):
            indent = dedent_string(
                indent, self.indent_using_tabs, self.space_indent_width
            )

        return indent + extra_indent, 0

    def smartNewline(self):
        """Insert a newline with smart indentation based on tree-sitter parse tree"""
        # This depends on syntax analysis, so I want to figure out
        # what to do before I edit and possibly break syntax

        citer = self.editor.citer
        istrs = []
        for cursor in citer.iterate_cursors(no_position_update=True):
            if cursor.hasSelection():
                cursor.setPosition(cursor.selectionStart())
            istrs.append(self._get_newline_indent(cursor))

        for i, cursor in enumerate(citer.iterate_cursors()):
            if cursor.hasSelection():
                citer.update_offset(cursor.selectionStart() - cursor.selectionEnd())
                cursor.removeSelectedText()
            indent_str, move = istrs[i]
            cursor.insertText("\n" + indent_str)
            if move < 0:
                cursor.movePosition(MO.Left, MM.MoveAnchor, -move)
            elif move > 0:
                cursor.movePosition(MO.Right, MM.MoveAnchor, move)
            citer.update_offset(len16(indent_str) + 1)
            citer.cursor_completed()

    def insertIndent(self):
        """Indent at the given cursor, either a single line or all the lines in a selection"""
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
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
                cursor.setPosition(start_pos + ins_size, MM.KeepAnchor)
                citer.cursor_completed()

    def unindent(self):
        """Unindent the given cursor, either a single line or all the lines in a selection"""
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
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
            cursor.setPosition(start_pos + ins_size, MM.KeepAnchor)
            citer.cursor_completed()

    def smartBackspace(self):
        """If backspacing at an the end of indentation, remove an entire "tab" of
        spaces. Otherwise just do a regular backspace
        """
        if self.indent_using_tabs:
            return
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
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
            cursor.movePosition(MO.Left, MM.KeepAnchor, delete)
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
        for cursor in citer.iterate_cursors():
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
            cursor.movePosition(MO.StartOfLine)
            cursor.movePosition(MO.EndOfLine, MM.KeepAnchor)

            oldlen = cursor.selectionEnd() - cursor.selectionStart()
            newtxt = dedented_indent + bracket
            newlen = len16(newtxt)
            cursor.insertText(dedented_indent + bracket)

            citer.update_offset(newlen - oldlen)
            citer.cursor_completed()
