from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore, QtGui

from ..gui_colors import GuiColors, gui_color
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class Overscroll(Behavior):
    """Behavior that allows scrolling past the end of the document"""

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._brush = QtGui.QBrush(QtCore.Qt.BrushStyle.SolidPattern)
        self._set_colors({})
        self._pen = QtGui.QPen(QtCore.Qt.PenStyle.NoPen)

        # Track the scroll position if the scroll position gets clamped
        # to the "normal" scroll range, so we can restore it afterwards
        self._cur_scroll = 0
        self._was_clamped = False

        self.editor.verticalScrollBar().valueChanged.connect(self.track_scroll)
        self.editor.verticalScrollBar().rangeChanged.connect(self.on_range_changed)
        self.editor.document().contentsChanged.connect(self.update_extra_scroll)

        self.update_extra_scroll()
        self.editor.behaviorPaint.connect(
            self.paint_outside_document, QtCore.Qt.ConnectionType.DirectConnection
        )
        self.watch_options({"colors": self._set_colors})
        self.apply_all_options()

    def track_scroll(self, value: int) -> None:
        sb = self.editor.verticalScrollBar()
        self._was_clamped = value == sb.maximum() and self._cur_scroll > sb.maximum()
        self._cur_scroll = value

    def update_extra_scroll(self) -> None:
        """Let the last line scroll up to the top of the viewport"""
        sb = self.editor.verticalScrollBar()
        newmax = self.editor.document().blockCount() - 1
        if sb.maximum() != newmax:
            sb.setMaximum(newmax)

    def on_range_changed(self) -> None:
        """Put back the extra scroll range, and a scroll position Qt clamped"""
        saved_value = self._cur_scroll
        update = self._was_clamped
        self.update_extra_scroll()
        if update:
            sb = self.editor.verticalScrollBar()
            sb.setValue(saved_value)

    def _set_colors(self, colors: GuiColors) -> None:
        # Unlike the other gui colors, the default depends on the background
        if "outside_bg" in colors:
            self._brush.setColor(QtGui.QColor(colors["outside_bg"]))
        else:
            self._brush.setColor(gui_color(colors, "bg").darker(120))
        self.editor.viewport().update()

    def paint_outside_document(
        self, _event: QtGui.QPaintEvent, painter: QtGui.QPainter
    ) -> None:
        """Shade the space below the last line"""
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
            painter.setPen(self._pen)

            oob_rect = QtCore.QRect(
                0,
                int(last_rect.bottom()),
                int(viewport_rect.width()),
                int(viewport_rect.height() - last_rect.bottom()),
            )
            painter.drawRect(oob_rect)
        finally:
            painter.restore()

    def remove(self) -> None:
        """Set the scroll range back to the line count"""
        super().remove()
        self.editor.behaviorPaint.disconnect(self.paint_outside_document)
        sb = self.editor.verticalScrollBar()
        sb.valueChanged.disconnect(self.track_scroll)
        sb.rangeChanged.disconnect(self.on_range_changed)
        self.editor.document().contentsChanged.disconnect(self.update_extra_scroll)
        viewport_height = self.editor.viewport().height()
        line_height = self.editor.fontMetrics().lineSpacing()
        visible_line_count = viewport_height // line_height
        total_line_count = self.editor.document().blockCount()
        sb.setMaximum(total_line_count - visible_line_count)
