from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore, QtGui

from ..gui_colors import GuiColors, gui_color
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
            {"font": self.line_number_area.setFont, "colors": self._set_colors}
        )

    def _set_colors(self, colors: GuiColors) -> None:
        self.line_number_area.set_gutter_colors(
            gui_color(colors, "gutter_fg"), gui_color(colors, "gutter")
        )

    def remove(self) -> None:
        super().remove()
        self.line_number_area.remove()
