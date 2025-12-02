from __future__ import annotations
from Qt.QtWidgets import QPlainTextEdit, QWidget
from Qt.QtGui import QKeySequence, QTextCursor, QKeyEvent, QFontMetrics, QTextBlock
from Qt.QtCore import Qt
from Qt import QtGui, QtCore
from typing import Callable, Optional
from .line_tracker import TrackedDocument, SyntaxHighlighter
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
        self.update_line_number_area_width(0)

    def sizeHint(self):
        return QtCore.QSize(self.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.line_number_area_paint_event(event)

    def line_number_area_width(self):
        digits = len(str(max(1, self.editor.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.editor.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.editor.line_number_area.scroll(0, dy)
        else:
            self.editor.line_number_area.update(
                0, rect.y(), self.editor.line_number_area.width(), rect.height()
            )
        if rect.contains(self.editor.viewport().rect()):
            self.update_line_number_area_width(0)

    def line_number_area_paint_event(self, event):
        painter = QtGui.QPainter(self.editor.line_number_area)
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
                    self.editor.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1


def hk(key, mods=None):
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
    single = kd.get(key)
    if single is not None:
        return single

    seqval = int(key)
    if mods is not None:
        seqval |= int(mods)
    return QKeySequence(seqval).toString(QKeySequence.PortableText)


class CodeEditor(QPlainTextEdit):
    def __init__(self, space_indent_width=4, tab_indent_width=8, parent=None):
        super().__init__(parent=parent)
        self._doc = TrackedDocument()
        self.setDocument(self._doc)
        self._space_indent_width = space_indent_width
        self._tab_indent_width = tab_indent_width
        self._ts_prediction: dict[int, QTextBlock] = {}

        # Create tree manager with source callback
        language = Language(tspython.language())
        self.tree_manager = TreeManager(language, self._treesitter_source_callback)

        # Create highlighter with tree manager
        self.highlighter = SyntaxHighlighter(
            self,
            self.tree_manager,
            tspython.HIGHLIGHTS_QUERY,
            FORMAT_SPECS,
        )

        # Create syntax analyzer (shares tree manager with highlighter)
        self.syntax_analyzer = SyntaxAnalyzer(self.tree_manager, self._doc)

        metrics = QFontMetrics(self.font())
        self.setTabStopWidth(self.tab_indent_width * metrics.width(" "))

        self.indent_using_tabs = False
        self.line_number_area = LineNumberArea(self)

        # TODO: Make the cursor stuff tell the document that it's making changes

        # Hotkeys
        self.hotkeys: dict[str, Callable[[QTextCursor], bool]] = {
            hk(Qt.Key.Key_Tab): self.insertIndent,
            hk(Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier): self.unindent,
            hk(Qt.Key.Key_Backspace): self.smartBackspace,
            hk(Qt.Key.Key_Return): self.smartNewline,
            hk(Qt.Key.Key_Enter): self.smartNewline,
        }

    @property
    def space_indent_width(self):
        return self._space_indent_width

    @space_indent_width.setter
    def space_indent_width(self, val):
        self._space_indent_width = val

    @property
    def tab_indent_width(self):
        return self._tab_indent_width

    @tab_indent_width.setter
    def tab_indent_width(self, val):
        self._tab_indent_width = val
        metrics = QFontMetrics(self.font())
        self.setTabStopWidth(self.tab_indent_width * metrics.width(" "))

    def document(self) -> TrackedDocument:
        doc = super().document()
        if not isinstance(doc, TrackedDocument):
            raise ValueError("This syntax highlighter only works with TrackedDocument")
        return doc

    def _treesitter_source_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """Provide source bytes to tree-sitter parser

        A callback for efficient access to the underlying byte data without duplicating it
        """
        curblock: Optional[QTextBlock] = self._ts_prediction.get(ts_point.row)
        if curblock is None:
            try:
                curblock = self.document().findBlockByNumber(ts_point.row)
            except IndexError:
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
        func = self.hotkeys.get(hk(key, modifiers))
        if func is not None:
            cursor = self.textCursor()
            if func(cursor):
                self.setTextCursor(cursor)
                return

        # Check for closing brackets that should trigger auto-dedent
        text = event.text()
        if text in (']', ')', '}'):
            cursor = self.textCursor()
            if self.smartClosingBracket(cursor, text):
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    def resizeEvent(self, e):
        """Handle resize events to update line number area geometry"""
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QtCore.QRect(
                cr.left(),
                cr.top(),
                self.line_number_area.line_number_area_width(),
                cr.height(),
            )
        )

    def _expandToLines(self, cursor):
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

        self._expandToLines(cursor)
        text = cursor.selection().toPlainText()
        lines = text.split("\n")
        if self.indent_using_tabs:
            indent = "\t"
        else:
            indent = " " * self.space_indent_width
        lines = [indent + line if line.strip() != "" else line for line in lines]
        cursor.insertText("\n".join(lines))
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

    def unindent(self, cursor: QTextCursor) -> bool:
        """Unindent the given cursor, either a single line or all the lines in a selection"""
        self._expandToLines(cursor)
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

    def smartNewline(self, cursor: QTextCursor) -> bool:
        """Insert a newline with smart indentation based on tree-sitter parse tree"""
        # Get current line text and indentation
        block = cursor.block()
        line_text = block.text()
        stripped = line_text.lstrip()
        indent = line_text[: len(line_text) - len(stripped)]

        # Get cursor position
        line_num = block.blockNumber()
        col = cursor.positionInBlock()

        # Look at the position just before the cursor to find the statement we just finished
        # This handles the case where cursor is after a colon with no content yet
        lookup_col = max(0, col - 1) if col > 0 else 0

        # Determine indent action based on syntax analysis
        extra_indent = ""
        dedent = False

        # Check if we should add indent (opening block)
        should_indent = self.syntax_analyzer.should_indent_after_position(
            line_num, lookup_col
        )

        if should_indent:
            if self.indent_using_tabs:
                extra_indent = "\t"
            else:
                extra_indent = " " * self.space_indent_width

        # Check if we should dedent (closing block or return statement)
        elif self.syntax_analyzer.should_dedent_after_position(
            line_num, lookup_col, line_text
        ):
            dedent = True

        # Apply dedent if needed
        final_indent = indent
        if dedent:
            final_indent = self._dedent_string(indent)

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
        dedented_indent = self._dedent_string(indent)

        # Replace the entire line with dedented indent + bracket
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        cursor.insertText(dedented_indent + bracket)

        return True

    def _dedent_string(self, indent: str) -> str:
        """Remove one level of indentation from the indent string"""
        if self.indent_using_tabs:
            if indent.endswith("\t"):
                return indent[:-1]
        else:
            # Remove up to space_indent_width spaces from the end
            spaces_to_remove = min(self.space_indent_width, len(indent))
            # Count trailing spaces
            trailing_spaces = len(indent) - len(indent.rstrip(" "))
            actual_remove = min(spaces_to_remove, trailing_spaces)
            if actual_remove > 0:
                return indent[:-actual_remove]
        return indent

    def updateAllLines(self, newtxt):
        """Update the entire text range to the given text"""
        cursor = self.textCursor()
        numchars = self.document().characterCount()
        cursor.setPosition(0)
        cursor.setPosition(numchars, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(newtxt)

    def tabsToSpaces(self):
        """Convert leading tabs to spaces"""
        newlines = []
        for line in self.document().iter_line_range():
            stripped = line.lstrip("\t")
            tabcount = len(line) - len(stripped)
            if tabcount:
                line = " " * (self.space_indent_width * tabcount) + stripped
            newlines.append(line)
        self.updateAllLines("".join(newlines))

    def spacesToTabs(self):
        """Convert leading groups of spaces to tabs"""
        newlines = []
        for line in self.document().iter_line_range():
            stripped = line.lstrip(" ")
            spacecount = len(line) - len(stripped)
            tabcount = spacecount // self.space_indent_width
            spacecount = spacecount - (tabcount * self.space_indent_width)
            if tabcount:
                line = ("\t" * tabcount) + (" " * spacecount) + stripped
            newlines.append(line)
        self.updateAllLines("".join(newlines))
