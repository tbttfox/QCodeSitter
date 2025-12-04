from __future__ import annotations
from Qt.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from Qt.QtGui import (
    QFont,
    QKeySequence,
    QResizeEvent,
    QTextCursor,
    QKeyEvent,
    QFontMetrics,
    QTextBlock,
    QPaintEvent,
    QColor,
    QTextCharFormat,
)
from Qt.QtCore import QRect, Qt, QObject, Signal
from Qt import QtGui, QtCore
from typing import Callable, Optional, Union, Any, Collection
from .line_tracker import TrackedDocument
from .line_highlighter import TreeSitterHighlighter
import tree_sitter_python as tspython
from tree_sitter import Language, Point
from .hl_groups import FORMAT_SPECS
from .tree_manager import TreeManager
from .syntax_analyzer import SyntaxAnalyzer


class LineNumberArea(QWidget):
    """Handle the painting of a Line Number column"""

    # TODO: relative line numbers
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.editor: CodeEditor = editor
        self.line_area_bg_color = QtGui.QColor(40, 40, 40)
        self.line_area_fg_color = QtGui.QColor(150, 150, 150)

        self.editor.blockCountChanged.connect(self.update_line_number_area_width)
        self.editor.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width()

    def sizeHint(self):
        return QtCore.QSize(self.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent):
        self.line_number_area_paint_event(event)

    def line_number_area_width(self):
        digits = len(str(max(1, self.editor.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self):
        self.editor.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self.scroll(0, dy)
        else:
            self.update(
                0, rect.y(), self.width(), rect.height()
            )
        if rect.contains(self.editor.viewport().rect()):
            self.update_line_number_area_width()

    def line_number_area_paint_event(self, event: QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.fillRect(event.rect(), self.line_area_bg_color)

        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = (
            self.editor.blockBoundingGeometry(block)
            .translated(self.editor.contentOffset())
            .top()
        )
        bottom = top + self.editor.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(self.line_area_fg_color)
                painter.drawText(
                    0,
                    int(top),
                    self.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1


def hk(
    key: Union[Qt.Key, int],
    mods: Optional[Union[Qt.KeyboardModifier, Qt.KeyboardModifiers, int]] = None,
) -> str:
    """Build a hashable hotkey string"""
    # Ignore pure modifier presses
    # And handle the stupidity of backtab
    kd = {
        Qt.Key_Shift: "Shift",
        Qt.Key_Control: "Control",
        Qt.Key_Alt: "Alt",
        Qt.Key_Meta: "Meta",
        Qt.Key_Backtab: "Shift+Tab",
    }
    single = kd.get(key)  # type: ignore
    if single is not None:
        return single

    seqval = int(key)
    if mods is not None:
        seqval |= int(mods)
    return QKeySequence(seqval).toString(QKeySequence.PortableText)


def dedent_string(indent: str, indent_using_tabs: bool, space_indent_width: int) -> str:
    """Remove one level of indentation from the indent string"""
    if indent_using_tabs:
        if indent.endswith("\t"):
            return indent[:-1]
    else:
        # Remove up to space_indent_width spaces from the end
        spaces_to_remove = min(space_indent_width, len(indent))
        # Count trailing spaces
        trailing_spaces = len(indent) - len(indent.rstrip(" "))
        actual_remove = min(spaces_to_remove, trailing_spaces)
        if actual_remove > 0:
            return indent[:-actual_remove]
    return indent


class EditorOptions(QObject):
    optionsUpdated = Signal(list)  # list of str

    def __init__(self, opts: Optional[dict[str, Any]] = None):
        super().__init__()
        if opts is None:
            opts = {}
        self._options: dict[str, Any] = {}

    def __getitem__(self, key: str):
        return self._options[key]

    def __setitem__(self, key: str, value):
        self._options[key] = value
        self.optionsUpdated.emit([key])

    def __contains__(self, key: str) -> bool:
        return key in self._options

    def update(self, opts: dict[str, Any]):
        self._options.update(opts)
        self.optionsUpdated.emit(list(opts.keys()))


class Behavior:
    def __init__(self, editor: CodeEditor, listen: set[str]):
        self.editor: CodeEditor = editor
        self.options: EditorOptions = editor.options
        self.listen: set[str] = listen
        self.options.optionsUpdated.connect(self.updateOptions)
        self.updateOptions(self.listen)

    def updateOptions(self, keys: Collection[str]):
        carekeys = set(keys) & self.listen
        for key in carekeys:
            setattr(self, key, self.options[key])


class HasKeyPress:
    def keyPressEvent(self, event: QKeyEvent, hotkey: str) -> bool:
        return False


class HasResize:
    def resizeEvent(self, event: QResizeEvent) -> bool:
        return False


class SmartIndent(HasKeyPress, Behavior):
    def __init__(self, editor: CodeEditor):
        self.space_indent_width: int = 4
        self._tab_indent_width: int = 4
        self.indent_using_tabs: bool = False
        super().__init__(
            editor,
            {"space_indent_width", "tab_indent_width", "indent_using_tabs", "font"},
        )

        self.hotkeys: dict[str, Callable[[QTextCursor], bool]] = {
            hk(Qt.Key.Key_Tab): self.insertIndent,
            hk(Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier): self.unindent,
            hk(Qt.Key.Key_Return): self.smartNewline,
            hk(Qt.Key.Key_Backspace): self.smartBackspace,
        }

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


class HighlightMatchingBrackets(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor, set())
        self.editor.cursorPositionChanged.connect(self.highlight_matching_brackets)

    def highlight_matching_brackets(self):
        """Highlight matching brackets/parens/braces using tree-sitter"""
        extra_selections = []

        # First add occurrence highlights if any text is selected
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        if selected_text and len(selected_text) >= 2 and len(selected_text) <= 100:
            format = QTextCharFormat()
            format.setBackground(QColor(255, 255, 0, 80))

            doc = self.editor.document()
            search_cursor = QTextCursor(doc)

            while True:
                search_cursor = doc.find(selected_text, search_cursor)
                if search_cursor.isNull():
                    break

                if (
                    search_cursor.position() != cursor.position()
                    or search_cursor.anchor() != cursor.anchor()
                ):
                    selection = QTextEdit.ExtraSelection()
                    selection.cursor = search_cursor
                    selection.format = format
                    extra_selections.append(selection)

        # Now check for bracket matching
        if self.editor.tree_manager.tree is None:
            self.editor.setExtraSelections(extra_selections)
            return

        cursor = self.editor.textCursor()
        pos = cursor.position()
        block = cursor.block()
        block_start = block.position()
        col = pos - block_start

        # Check character before and after cursor
        text = block.text()
        bracket_chars = "()[]{}"
        quote_chars = "'\""
        all_match_chars = bracket_chars + quote_chars
        opening_brackets = "([{"
        bracket_pairs = {"(": ")", "[": "]", "{": "}", ")": "(", "]": "[", "}": "{"}

        match_char = None
        match_pos = None

        # Check character before cursor (preferred)
        if col > 0 and text[col - 1] in all_match_chars:
            match_char = text[col - 1]
            match_pos = pos - 1
        # Check character after cursor
        elif col < len(text) and text[col] in all_match_chars:
            match_char = text[col]
            match_pos = pos

        if match_char is None or match_pos is None:
            self.editor.setExtraSelections(extra_selections)
            return

        # Convert character position to byte offset
        # Find which block contains this character position
        try:
            match_block = self.editor._doc.findBlock(match_pos)
            match_block_start = match_block.position()
            match_char_col = match_pos - match_block_start
            match_row = match_block.blockNumber()

            # Convert character column to byte column
            match_text = match_block.text()
            match_byte_col = len(match_text[:match_char_col].encode("utf-8"))

            # Convert row/col to byte offset using point_to_byte
            match_byte = self.editor._doc.point_to_byte(
                Point(match_row, match_byte_col)
            )
        except (IndexError, ValueError):
            self.editor.setExtraSelections(extra_selections)
            return

        # Get the node at the match position
        node = self.editor.tree_manager.get_node_at_point(match_byte)
        if node is None:
            self.editor.setExtraSelections(extra_selections)
            return

        # Handle quotes differently from brackets
        if match_char in quote_chars:
            # For quotes, we need to find the full string node (not just string_start/string_end)
            # Walk up to find a string node, but if we find string_start or string_end, keep going up
            string_node = node
            while string_node:
                # We want the parent 'string' node, not the child 'string_start'/'string_end' nodes
                if string_node.type == "string":
                    break
                string_node = string_node.parent

            if string_node is None:
                self.editor.setExtraSelections(extra_selections)
                return

            # For strings, highlight the opening and closing quotes
            # Get the string content from the document
            try:
                string_start_char = self.editor._doc.byte_to_char(
                    string_node.start_byte
                )
                string_end_char = self.editor._doc.byte_to_char(string_node.end_byte)
            except (IndexError, ValueError):
                self.editor.setExtraSelections(extra_selections)
                return

            # Get the actual string text to determine quote length (handle triple quotes)
            string_cursor = self.editor.textCursor()
            string_cursor.setPosition(string_start_char)
            string_cursor.setPosition(string_end_char, QTextCursor.KeepAnchor)
            string_text = string_cursor.selectedText()

            # Detect quote type (single/double/triple)
            quote_len = (
                3
                if string_text.startswith('"""') or string_text.startswith("'''")
                else 1
            )

            # Determine if cursor is at opening or closing quote
            # match_pos is the position of the quote character itself
            opening_end = string_start_char + quote_len
            closing_start = string_end_char - quote_len

            # Check if the quote at match_pos is within the opening quotes range
            cursor_at_opening = string_start_char <= match_pos < opening_end
            # Check if the quote at match_pos is within the closing quotes range
            cursor_at_closing = closing_start <= match_pos < string_end_char

            # Create highlight format
            quote_format = QTextCharFormat()
            quote_format.setBackground(QColor(200, 200, 200))  # Light gray

            # Determine which quotes to highlight based on cursor position
            # If cursor is at opening quote, highlight opening and closing
            # If cursor is at closing quote, highlight closing and opening
            # If cursor is somehow not at either (shouldn't happen), highlight both
            if cursor_at_opening or not cursor_at_closing:
                # Cursor is at opening quote (or default case)
                cursor_quote_start = string_start_char
                cursor_quote_end = opening_end
                match_quote_start = closing_start
                match_quote_end = string_end_char
            else:
                # Cursor is at closing quote
                cursor_quote_start = closing_start
                cursor_quote_end = string_end_char
                match_quote_start = string_start_char
                match_quote_end = opening_end

            # Highlight quote at cursor
            cursor1 = self.editor.textCursor()
            cursor1.setPosition(cursor_quote_start)
            cursor1.setPosition(cursor_quote_end, QTextCursor.KeepAnchor)
            selection1 = QTextEdit.ExtraSelection()
            selection1.cursor = cursor1
            selection1.format = quote_format
            extra_selections.append(selection1)

            # Highlight matching quote
            cursor2 = self.editor.textCursor()
            cursor2.setPosition(match_quote_start)
            cursor2.setPosition(match_quote_end, QTextCursor.KeepAnchor)
            selection2 = QTextEdit.ExtraSelection()
            selection2.cursor = cursor2
            selection2.format = quote_format
            extra_selections.append(selection2)

            self.editor.setExtraSelections(extra_selections)
            return

        # Handle brackets
        if node.type not in bracket_chars:
            self.editor.setExtraSelections(extra_selections)
            return

        # Find the matching bracket
        # For tree-sitter, matching brackets are siblings with the same parent
        matching_node = None
        parent = node.parent

        if parent is not None:
            matching_bracket_type = bracket_pairs[match_char]

            # Search siblings for the matching bracket
            for sibling in parent.children:
                if sibling.type == matching_bracket_type:
                    # Found a potential match
                    # For opening brackets, find the matching closing bracket (comes after)
                    if match_char in opening_brackets:
                        if sibling.start_byte > node.start_byte:
                            matching_node = sibling
                            break
                    # For closing brackets, find the matching opening bracket (comes before)
                    else:
                        if sibling.start_byte < node.start_byte:
                            matching_node = sibling

        if matching_node is None:
            self.editor.setExtraSelections(extra_selections)
            return

        # Convert byte positions to character positions
        try:
            node_start_char = self.editor._doc.byte_to_char(node.start_byte)
            node_end_char = self.editor._doc.byte_to_char(node.end_byte)
            match_start_char = self.editor._doc.byte_to_char(matching_node.start_byte)
            match_end_char = self.editor._doc.byte_to_char(matching_node.end_byte)
        except (IndexError, ValueError):
            self.editor.setExtraSelections(extra_selections)
            return

        # Create highlight format
        bracket_format = QTextCharFormat()
        bracket_format.setBackground(QColor(200, 200, 200))  # Light gray

        # Highlight the bracket under/near cursor
        cursor1 = self.editor.textCursor()
        cursor1.setPosition(node_start_char)
        cursor1.setPosition(node_end_char, QTextCursor.KeepAnchor)
        selection1 = QTextEdit.ExtraSelection()
        selection1.cursor = cursor1
        selection1.format = bracket_format
        extra_selections.append(selection1)

        # Highlight the matching bracket
        cursor2 = self.editor.textCursor()
        cursor2.setPosition(match_start_char)
        cursor2.setPosition(match_end_char, QTextCursor.KeepAnchor)
        selection2 = QTextEdit.ExtraSelection()
        selection2.cursor = cursor2
        selection2.format = bracket_format
        extra_selections.append(selection2)

        self.editor.setExtraSelections(extra_selections)


class HighlightMatchingSelection(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor, set())
        self.editor.selectionChanged.connect(self.highlight_occurrences)

    def highlight_occurrences(self):
        """Highlight all occurrences of the currently selected text"""
        extra_selections = []

        # Get current selection
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        # Only highlight if there's a selection and it's not too long
        # Also require at least 2 characters to avoid highlighting single chars
        if selected_text and len(selected_text) >= 2 and len(selected_text) <= 100:
            # Create format for highlighting occurrences
            format = QTextCharFormat()
            format.setBackground(
                QColor(255, 255, 0, 80)
            )  # Light yellow with transparency

            # Find all occurrences
            doc = self.editor.document()
            search_cursor = QTextCursor(doc)

            while True:
                search_cursor = doc.find(selected_text, search_cursor)
                if search_cursor.isNull():
                    break

                # Don't highlight the current selection itself
                if (
                    search_cursor.position() != cursor.position()
                    or search_cursor.anchor() != cursor.anchor()
                ):
                    selection = QTextEdit.ExtraSelection()
                    selection.cursor = search_cursor
                    selection.format = format
                    extra_selections.append(selection)

        self.editor.setExtraSelections(extra_selections)


class LineNumberBehvior(HasResize, Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor, set())
        self.line_number_area: LineNumberArea = LineNumberArea(self.editor)

    def resizeEvent(self, e: QResizeEvent):
        """Handle resize events to update line number area geometry"""
        cr = self.editor.contentsRect()
        self.line_number_area.setGeometry(
            QtCore.QRect(
                cr.left(),
                cr.top(),
                self.line_number_area.line_number_area_width(),
                cr.height(),
            )
        )


class CodeEditor(QPlainTextEdit):
    def __init__(
        self,
        space_indent_width=4,
        tab_indent_width=8,
        indent_using_tabs=False,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._doc: TrackedDocument = TrackedDocument()
        self.setDocument(self._doc)

        # TODO: Make options do the option thing
        self.options = EditorOptions()
        self.options.update(
            {
                "font": self.font(),
                "space_indent_width": space_indent_width,
                "tab_indent_width": tab_indent_width,
                "indent_using_tabs": indent_using_tabs,
            }
        )

        self._ts_prediction: dict[int, QTextBlock] = {}

        # Create tree manager with source callback
        language = Language(tspython.language())
        self.tree_manager: TreeManager = TreeManager(
            language, self._treesitter_source_callback
        )

        self.highlighter = TreeSitterHighlighter(
            self._doc,
            self.tree_manager,
            tspython.HIGHLIGHTS_QUERY,
            FORMAT_SPECS,
        )

        # Create syntax analyzer (shares tree manager with highlighter)
        self.syntax_analyzer: SyntaxAnalyzer = SyntaxAnalyzer(
            self.tree_manager, self._doc
        )

        # Hotkeys
        self.hotkeys: dict[str, Callable[[QTextCursor], bool]] = {}

        self._behaviors: list[Behavior] = []
        self._keyPressBehaviors: list[HasKeyPress] = []
        self._resizeBehaviors: list[HasResize] = []

        self.addBehavior(SmartIndent(self))
        self.addBehavior(HighlightMatchingBrackets(self))
        self.addBehavior(HighlightMatchingSelection(self))
        self.addBehavior(LineNumberBehvior(self))

    def addBehavior(self, behavior: Behavior):
        if isinstance(behavior, HasKeyPress):
            self._keyPressBehaviors.append(behavior)
        if isinstance(behavior, HasResize):
            self._resizeBehaviors.append(behavior)
        self._behaviors.append(behavior)

    def document(self) -> TrackedDocument:
        doc = super().document()
        if not isinstance(doc, TrackedDocument):
            raise ValueError("This syntax highlighter only works with TrackedDocument")
        return doc

    def _treesitter_source_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """Provide source bytes to tree-sitter parser

        A callback for efficient access to the underlying byte data without duplicating it
        """
        # Clear cache at the start of each parse (when row 0 is requested)
        # This ensures we don't use stale block references after document edits
        if ts_point.row == 0:
            self._ts_prediction = {}

        curblock: Optional[QTextBlock] = self._ts_prediction.get(ts_point.row)
        if curblock is None:
            try:
                curblock = self.document().findBlockByNumber(ts_point.row)
            except IndexError:
                self._ts_prediction = {}
                return b""

        # Check if block is valid (can be invalid after undo)
        if not curblock.isValid():
            self._ts_prediction = {}
            return b""

        self._ts_prediction[ts_point.row] = curblock
        nxt = curblock.next()
        self._ts_prediction[ts_point.row + 1] = nxt
        suffix = b"\n" if nxt.isValid() else b""
        linebytes = curblock.text().encode() + suffix

        return linebytes[ts_point.column :]

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        hotkey = hk(key, modifiers)

        func = self.hotkeys.get(hotkey)
        if func is not None:
            cursor = self.textCursor()
            if func(cursor):
                self.setTextCursor(cursor)
                return

        accepted = False
        for behavior in self._keyPressBehaviors:
            acc = behavior.keyPressEvent(event, hotkey)
            if accepted and acc:
                print(f"WARNING: Multiple behaviors handle the same hotkey: {hotkey}")
            accepted |= acc

        if accepted:
            return

        super().keyPressEvent(event)

    def resizeEvent(self, e: QResizeEvent):
        """Handle resize events to update line number area geometry"""
        super().resizeEvent(e)
        for behavior in self._resizeBehaviors:
            behavior.resizeEvent(e)

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

    def updateAllLines(self, newtxt: str):
        """Update the entire text range to the given text"""
        cursor = self.textCursor()
        numchars = self.document().characterCount()
        cursor.setPosition(0)
        cursor.setPosition(numchars, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(newtxt)
