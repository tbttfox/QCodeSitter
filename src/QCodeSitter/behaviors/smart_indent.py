from __future__ import annotations
from . import HasKeyPress, Behavior
from ..utils import dedent_string
from ..hotkey_manager import HotkeySlot, HotkeyGroup, hk
from ..multi_cursor_manager import CursorState
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
        self.hotkeys: dict[str, Callable[[], bool]] = {
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
        self.editor.setTabStopDistance(
            self.tab_indent_width * metrics.horizontalAdvance(" ")
        )

    def _font(self, _val: QFont):
        metrics = QFontMetrics(self.editor.font())
        self.editor.setTabStopDistance(
            self.tab_indent_width * metrics.horizontalAdvance(" ")
        )

    font = property(None, _font)

    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        if self.editor.multi_cursor_manager.is_active():
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                return self._smart_newline_multi_cursor()
            # Let other keys be handled by multi-cursor manager
            return False

        # Check for closing brackets that should trigger auto-dedent
        func = self.hotkeys.get(hotkey)
        print("SmartIndent", hotkey, func)
        if func is not None:
            if func():
                return True

        text = event.text()
        if text in ("]", ")", "}"):
            if self.smartClosingBracket(text):
                return True
        return False

    def smartNewline(self) -> bool:
        """Insert a newline with smart indentation based on tree-sitter parse tree"""
        if self.editor is None:
            return False
        cursor = self.editor.textCursor()
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
            self.editor.setTextCursor(cursor)
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
            self.editor.setTextCursor(cursor)
            return True

        # Look at the position just before the cursor to find the statement we just finished
        # This handles the case where cursor is after a colon with no content yet
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

        # Insert newline and indentation
        cursor.insertText("\n" + final_indent + extra_indent)
        self.editor.setTextCursor(cursor)
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

    def _smart_newline_multi_cursor(self) -> bool:
        """Insert smart newlines at all cursor positions"""
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
        inserted_texts = []  # Track what was inserted at each position

        for cursor_state, _original_index in sorted_with_index:
            if cursor_state == primary:
                primary_index = len(new_positions)
            qt_cursor.setPosition(cursor_state.position)
            block = qt_cursor.block()
            line_text = block.text()
            stripped = line_text.lstrip()
            indent = line_text[: len(line_text) - len(stripped)]

            line_num = block.blockNumber()
            col = qt_cursor.positionInBlock()

            # Calculate indentation similar to single cursor
            extra_indent = ""
            dedent = False
            text_to_insert = ""

            if stripped == "":
                # Empty line - just copy indent
                text_to_insert = "\n" + indent
            elif col == 0:
                # At beginning of line
                prev_block = block.previous()
                if prev_block.isValid():
                    prev_text = prev_block.text()
                    prev_stripped = prev_text.lstrip()
                    prev_indent = prev_text[: len(prev_text) - len(prev_stripped)]
                    text_to_insert = "\n" + prev_indent
                else:
                    text_to_insert = "\n"
            else:
                # Normal case - check syntax
                lookup_col = max(0, col - 1) if col > 0 else 0

                saz = self.editor.syntax_analyzer
                if saz.should_indent_after_position(line_num, lookup_col):
                    if self.indent_using_tabs:
                        extra_indent = "\t"
                    else:
                        extra_indent = " " * self.space_indent_width
                elif saz.should_dedent_after_position(line_num, lookup_col, line_text):
                    dedent = True

                final_indent = indent
                if dedent:
                    final_indent = dedent_string(
                        indent, self.indent_using_tabs, self.space_indent_width
                    )

                text_to_insert = "\n" + final_indent + extra_indent

            qt_cursor.insertText(text_to_insert)
            inserted_texts.append(text_to_insert)

            # Track new position (raw, will adjust later)
            new_pos = qt_cursor.position()
            new_positions.append((new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Now adjust all positions to account for the length changes
        # new_positions = [later_pos, earlier_pos, ...] (reverse doc order)
        # We iterate backwards and accumulate offsets for earlier positions
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):  # Iterate backwards
            pos = new_positions[i]
            # This position needs to be adjusted by all the edits that happened AFTER it (earlier in the loop)
            adjusted_pos = (pos[0] + cumulative_offset, pos[1] + cumulative_offset)
            adjusted_positions.insert(
                0, adjusted_pos
            )  # Insert at front to build in document order

            # Calculate the length change that THIS edit caused
            original_cursor = sorted_with_index[i][0]
            selection_length = abs(original_cursor.position - original_cursor.anchor)
            length_change = len(inserted_texts[i]) - selection_length
            cumulative_offset += length_change

        new_positions = adjusted_positions

        # Adjust primary index after reversal
        if primary_index is not None:
            primary_index = len(new_positions) - 1 - primary_index

        # Set primary cursor explicitly
        if primary_index is not None and primary_index < len(new_positions):
            # Move primary to front
            primary_cursor = new_positions.pop(primary_index)
            new_positions.insert(0, primary_cursor)

        # Update cursor positions
        cursor_states = [CursorState(anchor, pos) for anchor, pos in new_positions]
        self.editor.multi_cursor_manager._set_all_cursors(cursor_states)

        return True
