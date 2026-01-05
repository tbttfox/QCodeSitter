from __future__ import annotations
from . import HasResize, HasPaint, Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class Overscroll(HasResize, HasPaint, Behavior):
    """Behavior that allows scrolling past the end of the document

    This behavior:
    - Adds bottom viewport margin to enable scrolling past document end
    - Paints a custom background color below the document
    - Allows the last line to be positioned at the top of the viewport
    """

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"colors", "font"})

        # Default outside background color (will be updated by colors)
        self._brush = QtGui.QBrush(QtCore.Qt.BrushStyle.SolidPattern)
        self._brush.setColor(QtGui.QColor(40, 40, 40))

        self.editor.document().contentsChanged.connect(self.update_extra_scroll)
        self.update_extra_scroll()

        self.updateAll()

    def _colors(self, val):
        """Update colors when color options change"""
        if "outside_bg" in val:
            self._brush.setColor(QtGui.QColor(val["outside_bg"]))
        else:
            # Default to 50% darker than main background
            bg_color = QtGui.QColor(val["bg"])
            self._brush.setColor(bg_color.darker(150))

        # Trigger repaint
        self.editor.viewport().update()

    colors = property(None, _colors)

    def _font(self, newfont):
        """Update margin when font changes (affects line height)"""
        self.update_extra_scroll()

    font = property(None, _font)

    def update_extra_scroll(self):
        sb = self.editor.verticalScrollBar()
        viewport_height = self.editor.viewport().height()
        line_height = self.editor.fontMetrics().lineSpacing()
        visible_line_count = viewport_height // line_height
        total_line_count = self.editor.document().blockCount()
        extras = max(0, min(visible_line_count - 2, total_line_count - 1))
        sb.setMaximum(sb.maximum() + extras)

    def resizeEvent(self, e: QtGui.QResizeEvent):
        self.update_extra_scroll()

    def paintEvent(self, e: QtGui.QPaintEvent, painter: QtGui.QPainter):
        doc = self.editor.document()
        block = doc.lastBlock()

        if not block.isValid():
            return

        last_rect = self.editor.blockBoundingGeometry(block)
        last_rect.translate(self.editor.contentOffset())

        viewport_rect = QtCore.QRectF(self.editor.viewport().rect())
        if not viewport_rect.intersects(last_rect):
            return

        painter.save()
        try:
            painter.setBrush(self._brush)
            painter.setPen(QtGui.QPen())

            oob_rect = QtCore.QRect(
                0,
                int(last_rect.bottom()),
                int(viewport_rect.width()),
                int(viewport_rect.height() - last_rect.bottom()),
            )
            painter.drawRect(oob_rect)
        finally:
            painter.restore()

    def remove(self):
        """Set the scroll back to the line count"""
        total_line_count = self.editor.document().blockCount()
        self.editor.verticalScrollBar().setMaximum(total_line_count)
