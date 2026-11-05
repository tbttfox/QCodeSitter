from __future__ import annotations

from Qt import QtCore, QtGui, QtWidgets

from ..cursors.line_edits import replace_lines_at_cursors
from ..languages import IndentRules, language_spec
from ..tracked_document import utf16_to_index
from ..utils import KEY, MM, MO, add_menu_action, dedent_string, leading_whitespace
from . import Behavior

CLOSING_BRACKETS = ("]", ")", "}")


class SmartIndent(Behavior):
    """Syntax-aware indentation for Enter, Tab, Shift+Tab, Backspace and closing brackets

    The indent settings come from the options, and the indent rules come from
    the editor language's LanguageSpec
    """

    @property
    def _use_tabs(self) -> bool:
        return self.options["indent_using_tabs"]

    @property
    def _width(self) -> int:
        return self.options["space_indent_width"]

    def add_context_menu_actions(
        self, menu: QtWidgets.QMenu, pos: QtCore.QPoint
    ) -> None:
        add_menu_action(menu, "Indent", self.insert_indent, "Tab")
        add_menu_action(menu, "Unindent", self.unindent, "Shift+Tab")

    def indent_rules(self) -> IndentRules:
        spec = language_spec(self.editor.tree_manager.language)
        return spec.indent_rules(self.editor.tree_manager)

    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        key = event.key()
        if key == KEY.Key_Tab:
            self.insert_indent()
            return True
        if key == KEY.Key_Backtab:
            self.unindent()
            return True
        # These only handle some cursors, and leave the rest to the editor
        if key in (KEY.Key_Return, KEY.Key_Enter):
            self.smart_newline()
        elif key == KEY.Key_Backspace:
            self._smart_backspace()
        elif event.text() in CLOSING_BRACKETS:
            self._smart_closing_bracket(event.text())
        else:
            return False
        return self.editor.citer.all_completed()

    def _one_indent(self) -> str:
        return "\t" if self._use_tabs else " " * self._width

    def _dedent(self, indent: str) -> str:
        return dedent_string(indent, self._use_tabs, self._width)

    def _newline_indent(
        self, cursor: QtGui.QTextCursor, rules: IndentRules
    ) -> tuple[str, int]:
        """Work out the indentation to insert after a newline at the cursor

        Returns:
            The text to insert after the newline
            How far to move the cursor back from the end of that text
        """
        block = cursor.block()
        line_text = block.text()
        indent = leading_whitespace(line_text)
        col = cursor.positionInBlock()

        # At the start of a line, move the line down unchanged
        if col == 0:
            return "", 0

        # A blank line keeps its indentation
        if not line_text.strip():
            return indent, 0

        # Between a pair of brackets, put the closing bracket on its own line
        # below an indented empty line
        index = utf16_to_index(line_text, col)
        if line_text[index - 1 : index + 1] in self.options["indent_bracket_pairs"]:
            return indent + self._one_indent() + "\n" + indent, len(indent) + 1

        # Look at the character just before the cursor to find the statement we just finished
        row = block.blockNumber()
        if rules.should_indent_after(row, col - 1):
            return indent + self._one_indent(), 0
        if rules.should_dedent_after(row, col - 1):
            return self._dedent(indent), 0
        return indent, 0

    def smart_newline(self) -> None:
        """Insert a newline indented to suit the code around each cursor"""
        # Work out every indent before editing, because the edits change the tree
        citer = self.editor.citer
        rules = self.indent_rules()
        indents = []
        with self.editor.edit_session():
            for cursor in citer.read_cursors():
                if cursor.hasSelection():
                    cursor.setPosition(cursor.selectionStart())
                indents.append(self._newline_indent(cursor, rules))

            for i, cursor in enumerate(citer.iterate_cursors(complete_all=True)):
                indent_str, move_back = indents[i]
                cursor.insertText("\n" + indent_str)
                if move_back:
                    cursor.movePosition(MO.Left, MM.MoveAnchor, move_back)

    def insert_indent(self) -> None:
        """Indent to the next tab stop, or indent every cursor's lines if any selects

        A selection anywhere indents whole lines, so a cursor on a line that
        another cursor's selection indents doesn't indent it twice
        """
        citer = self.editor.citer
        width = self._width
        indent = self._one_indent()

        def indent_lines(lines: list[str]) -> list[str]:
            return [indent + ln if ln.strip() else ln for ln in lines]

        with self.editor.edit_session():
            if any(cursor.hasSelection() for cursor in citer.read_cursors()):
                replace_lines_at_cursors(citer, indent_lines)
                return
            for cursor in citer.iterate_cursors(complete_all=True):
                if self._use_tabs:
                    cursor.insertText("\t")
                else:
                    cursor.insertText(" " * (width - cursor.positionInBlock() % width))

    def unindent(self) -> None:
        """Remove one indent from every line of each cursor's selection or line"""
        citer = self.editor.citer
        width = self._width
        use_tabs = self._use_tabs

        def unindent_line(line: str) -> str:
            if use_tabs:
                return line.removeprefix("\t")
            return line[:width].lstrip(" ") + line[width:]

        with self.editor.edit_session():
            replace_lines_at_cursors(
                citer, lambda lines: [unindent_line(ln) for ln in lines]
            )

    def _smart_backspace(self) -> None:
        """Backspace over a whole indent when the cursor is in the indentation"""
        if self._use_tabs:
            return
        citer = self.editor.citer
        width = self._width
        for cursor in citer.iterate_cursors():
            col = cursor.positionInBlock()
            if cursor.hasSelection() or col == 0:
                continue
            # Spaces are one code unit each, so col is also the str index
            if set(cursor.block().text()[:col]) != {" "}:
                continue

            # Delete back to the previous tab stop
            cursor.movePosition(MO.Left, MM.KeepAnchor, col % width or width)
            cursor.removeSelectedText()
            citer.mark_cursor_completed()

    def _smart_closing_bracket(self, bracket: str) -> None:
        """Dedent a blank line when a closing bracket is typed on it"""
        citer = self.editor.citer
        for cursor in citer.iterate_cursors():
            if cursor.hasSelection():
                cursor.removeSelectedText()

            line_text = cursor.block().text()
            indent = leading_whitespace(line_text)
            if not indent or line_text.strip():
                continue

            cursor.movePosition(MO.StartOfLine)
            cursor.movePosition(MO.EndOfLine, MM.KeepAnchor)
            cursor.insertText(self._dedent(indent) + bracket)
            citer.mark_cursor_completed()
