from __future__ import annotations
from . import HasResize, Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore, QtWidgets

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


class LineNumberArea(QtWidgets.QWidget):
    """Handle the painting of a Line Number column"""

    # TODO: relative line numbers
    def __init__(self, editor: CodeEditor, fg: QtGui.QColor, bg: QtGui.QColor):
        super().__init__(editor)
        self.editor: CodeEditor = editor
        self.line_area_bg_color = bg
        self.line_area_fg_color = fg

        self.editor.blockCountChanged.connect(self.update_line_number_area_width)
        self.editor.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width()

    def setColors(self, fg: QtGui.QColor, bg: QtGui.QColor):
        self.line_area_fg_color = fg
        self.line_area_bg_color = bg

    def sizeHint(self):
        return QtCore.QSize(self.line_number_area_width(), 0)

    def paintEvent(self, event: QtGui.QPaintEvent):
        self.line_number_area_paint_event(event)

    def line_number_area_width(self):
        digits = len(str(max(1, self.editor.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self):
        # Check if code folding behavior exists and account for its width
        folding_width = 0
        from .code_folding import CodeFolding

        folding_behavior = self.editor.getBehavior(CodeFolding)
        if folding_behavior is not None:
            folding_width = folding_behavior.folding_area.width_hint()

        self.editor.setViewportMargins(
            self.line_number_area_width() + folding_width, 0, 0, 0
        )

    def clear_line_number_area_width(self):
        self.editor.setViewportMargins(0, 0, 0, 0)

    def update_line_number_area(self, rect: QtCore.QRect, dy: int):
        if dy:
            self.scroll(0, dy)
        else:
            self.update(0, rect.y(), self.width(), rect.height())
        if rect.contains(self.editor.viewport().rect()):
            self.update_line_number_area_width()

    def line_number_area_paint_event(self, event: QtGui.QPaintEvent):
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
                    QtCore.Qt.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1


class LineNumber(HasResize, Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"font", "colors"})
        self.line_number_area: LineNumberArea = LineNumberArea(
            self.editor,
            QtGui.QColor(150, 150, 150),
            QtGui.QColor(40, 40, 40),
        )
        if editor.isVisible() and not self.line_number_area.isVisible():
            self.line_number_area.setVisible(True)
            self.setLineGeo()

        self.updateAll()

    def _font(self, newfont):
        self.line_number_area.setFont(newfont)

    font = property(None, _font)

    def _colors(self, val):
        self.line_number_area.setColors(
            QtGui.QColor(val["gutter_fg"]), QtGui.QColor(val["gutter"])
        )

    colors = property(None, _colors)

    def resizeEvent(self, e: QtGui.QResizeEvent):
        self.setLineGeo()

    def setLineGeo(self):
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

    def remove(self):
        self.line_number_area.clear_line_number_area_width()
        self.line_number_area.deleteLater()
        self.line_number_area = None  # type: ignore
