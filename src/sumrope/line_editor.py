from __future__ import annotations
from Qt.QtWidgets import QPlainTextEdit, QWidget
from Qt.QtGui import QKeySequence, QTextCursor, QKeyEvent, QFontMetrics
from Qt.QtCore import Qt
from Qt import QtGui, QtCore
from typing import Callable
from .line_tracker import TrackedDocument, SyntaxHighlighter
import tree_sitter_python as tspython
from tree_sitter import Language
from .hl_groups import FORMAT_SPECS


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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.editor.line_number_area.setGeometry(
            QtCore.QRect(
                cr.left(), cr.top(), self.line_number_area_width(), cr.height()
            )
        )

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

        self.highlighter = SyntaxHighlighter(
            self,
            Language(tspython.language()),
            tspython.HIGHLIGHTS_QUERY,
            FORMAT_SPECS,
        )

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

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        func = self.hotkeys.get(hk(key, modifiers))
        if func is not None:
            cursor = self.textCursor()
            if func(cursor):
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

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

        cursor.beginEditBlock()
        self._expandToLines(cursor)
        text = cursor.selection().toPlainText()
        lines = text.split("\n")
        if self.indent_using_tabs:
            indent = "\t"
        else:
            indent = " " * self.space_indent_width
        lines = [indent + line if line.strip() != "" else line for line in lines]
        cursor.insertText("\n".join(lines))
        cursor.endEditBlock()
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
        cursor.beginEditBlock()
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
        cursor.endEditBlock()
        return True

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
