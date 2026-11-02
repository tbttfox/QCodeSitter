from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore, QtGui

from ..gutters import GutterWidget
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class LineNumberArea(GutterWidget):
    def width_hint(self) -> int:
        digits = len(str(max(1, self.editor.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(event.rect(), self.bg_color)
        painter.setPen(self.fg_color)
        for block, top, bottom in self.visible_blocks(event.rect().bottom()):
            if bottom >= event.rect().top():
                painter.drawText(
                    0,
                    int(top),
                    self.width() - 5,
                    self.fontMetrics().height(),
                    QtCore.Qt.AlignmentFlag.AlignRight,
                    str(block.blockNumber() + 1),
                )


class LineNumbers(Behavior):
    """A gutter showing the line numbers"""

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.line_number_area = LineNumberArea(self.editor)
        self.watch_options(
            {
                "font": self.line_number_area.setFont,
                "colors": self.line_number_area.set_gutter_colors,
            }
        )

    def on_remove(self) -> None:
        self.line_number_area.remove()
