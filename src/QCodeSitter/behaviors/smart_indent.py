from __future__ import annotations
from . import HasKeyPress, Behavior
from ..utils import dedent_string
from ..multi_cursor_manager import MultiCursorManager
from typing import TYPE_CHECKING
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

        self.setListen(
            {"space_indent_width", "tab_indent_width", "indent_using_tabs", "font"}
        )
        self.updateAll()

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

    def _calculate_newline_indent(
        self, line_num: int, col: int, line_text: str, indent: str
    ) -> str:
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
        stripped = line_text.lstrip()

        # Special case: if the current line is empty/whitespace-only, just copy the indentation
        if stripped == "":
            return indent

        # Special case: if cursor is at the beginning of the line
        if col == 0:
            # Use previous line's indentation if available
            block = self.editor.document().findBlockByNumber(line_num)
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

    def keyPressEvent(self, event: QKeyEvent) -> bool:
        # Special handling for Return/Enter key using unified cursor interface
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.editor.cursor.is_multi_mode:
                return self.smartNewline()
            else:
                return self._smart_newline_multi_cursor()

        # In multi-cursor mode, let other keys be handled by multi-cursor manager
        if self.editor.cursor.is_multi_mode:
            return False

        # Check for closing brackets that should trigger auto-dedent
        if event.key() == Qt.Key.Key_Tab:
            self.insertIndent()
            return True
        elif event.key() == Qt.Key.Key_Backtab:
            self.unindent()
            return True
        elif event.key() == Qt.Key.Key_Return:
            self.smartNewline()
            return True
        elif event.key() == Qt.Key.Key_Backspace:
            self.smartBackspace()
            return True

        text = event.text()
        if text in ("]", ")", "}"):
            if self.smartClosingBracket(text):
                return True
        return False

    def _get_newline_indent(self, cursor: QTextCursor):
        # Get current line text and indentation
        block = cursor.block()
        line_text = block.text()
        stripped = line_text.lstrip()
        indent = line_text[: len(line_text) - len(stripped)]

        # Get cursor position
        line_num = block.blockNumber()
        col = cursor.positionInBlock()

        # Calculate the indentation to insert using shared helper
        return self._calculate_newline_indent(line_num, col, line_text, indent)

    def smartNewline(self) -> bool:
        """Insert a newline with smart indentation based on tree-sitter parse tree"""
        cursor = self.editor.textCursor()
        indent_str = self._get_newline_indent(cursor)

        # Insert newline and indentation
        cursor.insertText(indent_str)
        self.editor.setTextCursor(cursor)
        return True

    def _smart_newline_multi_cursor(self) -> bool:
        """Insert smart newlines at all cursor positions"""
        # Get primary cursor before sorting
        primary = self.editor.multi_cursor_manager.get_primary_cursor()
        all_cursors, _primary_index = self.editor.multi_cursor_manager.get_all_cursors()

        # Sort reverse for insertions (back to front) but track primary
        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        primary_index = None
        inserted_texts = []  # Track what was inserted at each position
        original_cursors_list = []  # Track original cursors for position adjustment

        for cursor_state, _original_index in sorted_with_index:
            if cursor_state == primary:
                primary_index = len(inserted_texts)
            qt_cursor.setPosition(cursor_state.position)

            indent_str = self._get_newline_indent(qt_cursor)
            text_to_insert = "\n" + indent_str

            qt_cursor.insertText(text_to_insert)
            inserted_texts.append(text_to_insert)
            original_cursors_list.append(cursor_state)

        qt_cursor.endEditBlock()

        # Use shared utility to adjust positions after edits
        cursor_states = MultiCursorManager._adjust_positions_after_edits(
            original_cursors_list, inserted_texts, primary_index
        )
        self.editor.multi_cursor_manager._set_all_cursors(cursor_states)

        return True

    def smartClosingBracket(self, bracket: str) -> bool:
        """Auto-dedent when typing a closing bracket if the line only contains whitespace

        Args:
            cursor: The text cursor
            bracket: The closing bracket character (']', ')', or '}')

        Returns:
            True if we handled the bracket insertion, False to use default behavior
        """
        # This is only concerned with whitespace, so we don't have to deal with encoding
        # Only auto-dedent if we're at the end of a line that contains only whitespace
        cursor = self.editor.textCursor()

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

        self.editor.setTextCursor(cursor)
        return True

    def smartBackspace(self) -> bool:
        """If backspacing at an the end of indentation, remove an entire "tab" of
        spaces. Otherwise just do a regular backspace
        """
        if self.indent_using_tabs:
            return False
        cursor = self.editor.textCursor()

        if cursor.hasSelection():
            return False
        col = cursor.positionInBlock()
        if col == 0:
            return False  # normal backspace

        # Check if all preceding characters are spaces
        # This is only dealing with whitespace, so we don't have to worry about encoding
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
        self.editor.setTextCursor(cursor)
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
        self.editor.setPlainText("".join(newlines))

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
        self.editor.setPlainText("".join(newlines))

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

    def insertIndent(self) -> bool:
        """Indent at the given cursor, either a single line or all the lines in a selection"""
        cursor = self.editor.textCursor()
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
            self.editor.setTextCursor(cursor)
            return True

        self.expandCursorToLines(cursor)
        start_pos = cursor.selectionStart()
        end_pos = cursor.selectionEnd()
        text = cursor.selection().toPlainText()
        lines = text.split("\n")
        if self.indent_using_tabs:
            indent = "\t"
        else:
            indent = " " * self.space_indent_width
        lines = [indent + line if line.strip() != "" else line for line in lines]
        cursor.insertText("\n".join(lines))

        # Restore selection, adjusting for the added indent
        indent_added = len([line for line in lines if line.strip() != ""]) * len(indent)
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos + indent_added, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        return True

    def unindent(self) -> bool:
        """Unindent the given cursor, either a single line or all the lines in a selection"""
        cursor = self.editor.textCursor()
        self.expandCursorToLines(cursor)
        start_pos = cursor.selectionStart()
        end_pos = cursor.selectionEnd()
        text = cursor.selection().toPlainText()
        lines = text.split("\n")
        if self.indent_using_tabs:
            newlines = [line[1:] if line[0] == "\t" else line for line in lines]
            # Calculate removed indent: count lines that had a tab removed
            indent_removed = sum(
                1 for i, line in enumerate(lines) if len(line) > 0 and line[0] == "\t"
            )
        else:
            newlines = [
                line[: self.space_indent_width].lstrip(" ")
                + line[self.space_indent_width :]
                for line in lines
            ]
            # Calculate removed indent: count actual spaces removed from each line
            indent_removed = sum(
                len(lines[i]) - len(newlines[i]) for i in range(len(lines))
            )
        cursor.insertText("\n".join(newlines))

        # Restore selection, adjusting for the removed indent
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos - indent_removed, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        return True
