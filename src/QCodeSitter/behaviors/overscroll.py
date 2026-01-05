from __future__ import annotations
from . import HasResize, HasPaint, HasKeyPress, Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class Overscroll(HasPaint, HasKeyPress, Behavior):
    """Behavior that allows scrolling past the end of the document"""

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"colors"})

        # Default outside background color (will be updated by colors)
        self._brush = QtGui.QBrush(QtCore.Qt.BrushStyle.SolidPattern)
        self._brush.setColor(QtGui.QColor(40, 40, 40))

        # Track the scroll position to preserve it during resize
        self._cur_scroll = 0
        self._prev_scroll = 0
        self._action_scroll = 0
        self._saved_scroll_value = 0

        self.editor.verticalScrollBar().actionTriggered.connect(self.slider_action)
        self.editor.verticalScrollBar().valueChanged.connect(self.track_scroll)
        self.editor.verticalScrollBar().rangeChanged.connect(self.on_range_changed)
        self.editor.document().contentsChanged.connect(self.on_contents_changed)

        self.update_extra_scroll()

        self.updateAll()

    def on_contents_changed(self):
        self.update_extra_scroll()

    def slider_action(self):
        self._action_scroll = self.editor.verticalScrollBar().value()

    def track_scroll(self, value):
        self._prev_scroll = self._cur_scroll
        self._cur_scroll = value

    def keyPressEvent(self, event) -> bool:
        saved_value = self.editor.verticalScrollBar().value()
        self._prev_scroll = saved_value
        self._cur_scroll = saved_value
        return False

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

    def update_extra_scroll(self):
        sb = self.editor.verticalScrollBar()
        newmax = self.editor.document().blockCount() - 1
        if sb.maximum() != newmax:
            sb.setMaximum(newmax)

    def on_range_changed(self):
        """Handle range updates"""
        # This is annoying. I need to figure out which scroll updates come from
        # user input, and which come from Qt resetting the scroll bar
        # The best I was able to come up with was to keep track of the current
        # scroll, the previous scroll, and the scroll from actionTriggered
        # And if the previous scroll was an actionTriggered value, then use
        # the current scroll instead. There's probably an edge case somewhere
        # but it's better than anything else I've done
        # It MAY be possible to do this via subclassing a scrollbar
        saved_value = self._prev_scroll
        if self._action_scroll == saved_value:
            saved_value = self._cur_scroll

        self.update_extra_scroll()
        self.editor.verticalScrollBar().setValue(saved_value)
        self._prev_scroll = saved_value
        self._cur_scroll = saved_value

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
        sb = self.editor.verticalScrollBar()
        viewport_height = self.editor.viewport().height()
        line_height = self.editor.fontMetrics().lineSpacing()
        visible_line_count = viewport_height // line_height
        total_line_count = self.editor.document().blockCount()
        sb.setMaximum(total_line_count - visible_line_count)
