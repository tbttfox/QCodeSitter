from __future__ import annotations
from . import Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore
from ..gutter_widget import GutterWidget

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class LineNumberArea(GutterWidget):
    def __init__(self, editor: CodeEditor, fg: QtGui.QColor, bg: QtGui.QColor):
        super().__init__("LineNumberArea", editor)
        self.line_area_bg_color = bg
        self.line_area_fg_color = fg

        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_gutter)
        self.update_width()

    def setColors(self, fg: QtGui.QColor, bg: QtGui.QColor):
        self.line_area_fg_color = fg
        self.line_area_bg_color = bg

    def width_hint(self):
        digits = len(str(max(1, self.editor.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def paintEvent(self, event: QtGui.QPaintEvent):
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


class LineNumber(Behavior):
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
            self.line_number_area.set_gutter_geo()

        self.updateAll()

    def _font(self, newfont):
        self.line_number_area.setFont(newfont)

    font = property(None, _font)

    def _colors(self, val):
        self.line_number_area.setColors(
            QtGui.QColor(val["gutter_fg"]), QtGui.QColor(val["gutter"])
        )

    colors = property(None, _colors)

    def remove(self):
        self.line_number_area.clear_width()
        self.line_number_area.deleteLater()
        self.line_number_area = None  # type: ignore
