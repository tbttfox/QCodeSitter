from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore, QtGui, QtWidgets

from ..gui_colors import GuiColors, gui_color
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class MultiCursorPaint(Behavior):
    """Draws every cursor, including the secondary cursors of multi-cursor mode

    Qt's own cursor is hidden while this behavior is installed, and the primary
    cursor is drawn the same way as the others. The selections of the secondary
    cursors are shown as extra selections.
    """

    SOURCE = "multi_cursor"

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.cursor_width = 2
        self.watch_options({"colors": self._set_colors})
        self._qt_cursor_width = self.editor.cursorWidth()
        self.editor.setCursorWidth(0)

        self._blink_state = True
        self.blink_timer = QtCore.QTimer(self.editor)
        self.blink_timer.timeout.connect(self._update_blink)
        self.blink_timer.start(QtWidgets.QApplication.instance().cursorFlashTime() // 2)
        self.connect(
            self.editor.behaviorPaint,
            self.paint_cursors,
            QtCore.Qt.ConnectionType.DirectConnection,
        )
        self.connect(self.editor.cursors.changed, self.on_cursors_changed)

    def _set_colors(self, colors: GuiColors) -> None:
        self.primary_cursor_color = gui_color(colors, "primary_cursor")
        self.secondary_cursor_color = gui_color(colors, "secondary_cursor")
        self.secondary_selection_color = gui_color(colors, "secondary_selection")

    def on_cursors_changed(self) -> None:
        if self.editor.cursors.secondary:
            self._update_selections()
        else:
            self.editor.clear_selections(self.SOURCE)
        self.editor.viewport().update()

    def _update_selections(self) -> None:
        """Show the selections of every cursor as extra selections"""
        # In multi-cursor mode the primary selection is drawn like the others
        states = [*self.editor.cursors.secondary, self.editor.cursors.primary()]

        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(self.secondary_selection_color.lighter(150))
        doc = self.editor.document()
        selections = []
        for state in states:
            if state.hasSelection():
                selection = QtWidgets.QTextEdit.ExtraSelection()
                selection.format = fmt
                selection.cursor = state.build_cursor(doc)
                selections.append(selection)

        self.editor.set_selections(self.SOURCE, selections)

    def paint_cursors(self, _event: QtGui.QPaintEvent, painter: QtGui.QPainter) -> None:
        """Paint thin cursor lines for all cursors without selections"""
        if not self._blink_state:
            return
        painter.save()
        try:
            cursor = QtGui.QTextCursor(self.editor.document())
            for state in self.editor.cursors.secondary:
                if not state.hasSelection():
                    self._draw_cursor_at_position(
                        painter, cursor, state.position, self.secondary_cursor_color
                    )
            primary = self.editor.cursors.primary()
            if not primary.hasSelection():
                self._draw_cursor_at_position(
                    painter, cursor, primary.position, self.primary_cursor_color
                )
        finally:
            painter.restore()

    def _update_blink(self) -> None:
        if not self.editor.hasFocus():
            if self._blink_state:
                self._blink_state = False
                self.editor.viewport().update()
            return
        self._blink_state = not self._blink_state
        self.editor.viewport().update()

    def _draw_cursor_at_position(
        self,
        painter: QtGui.QPainter,
        cursor: QtGui.QTextCursor,
        position: int,
        color: QtGui.QColor,
    ) -> None:
        """Draw a cursor line at a document position, if it's in the viewport"""
        cursor.setPosition(position)
        cursor_rect = self.editor.cursorRect(cursor)
        if not self.editor.viewport().rect().intersects(cursor_rect):
            return

        pen = QtGui.QPen(color)
        pen.setWidth(self.cursor_width)
        painter.setPen(pen)
        painter.drawLine(cursor_rect.topLeft(), cursor_rect.bottomLeft())

    def remove(self) -> None:
        super().remove()
        self.blink_timer.stop()
        self.blink_timer.deleteLater()
        self.editor.clear_selections(self.SOURCE)
        self.editor.setCursorWidth(self._qt_cursor_width)
