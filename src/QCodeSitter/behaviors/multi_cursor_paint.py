from __future__ import annotations
from . import HasPaint, Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore, QtWidgets

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class MultiCursorPaint(HasPaint, Behavior):
    """Behavior that renders cursors with custom painting

    This behavior handles rendering of both the primary cursor and secondary
    cursors (when in multi-cursor mode). It uses:
    - Custom thin cursor lines for cursor positions (rendered via painting)
    - ExtraSelections for text selections (rendered via Qt's selection mechanism)

    The primary cursor is always drawn using this behavior, replacing the
    built-in Qt cursor which is hidden via setCursorWidth(0).
    """

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"colors"})

        # Cursor appearance
        self.cursor_width = 2
        self.primary_cursor_color: QtGui.QColor
        self.secondary_cursor_color: QtGui.QColor
        self.selection_color: QtGui.QColor
        self.bg_color: QtGui.QColor
        self._blink_state = True
        self.blink_timer = QtCore.QTimer(self.editor)
        self.blink_timer.timeout.connect(self._update_blink)
        self.blink_timer.start(QtWidgets.QApplication.instance().cursorFlashTime() // 2)
        self.updateAll()

    def _colors(self, val):
        """Update colors when color options change"""
        self.primary_cursor_color = QtGui.QColor(val.get("primary_cursor", "#FFFFFFFF"))
        self.secondary_cursor_color = QtGui.QColor(
            val.get("secondary_cursor", "#B4B4B4")
        )
        self.selection_color = QtGui.QColor(val.get("selection_color", "#B4B4B4"))

    colors = property(None, _colors)

    def update_visual(self):
        """Public method called by CodeEditor when cursors change"""
        # Update selections for cursors with text selected
        self._update_selections()

        # Trigger repaint for cursor lines
        self.editor.viewport().update()

    def _update_selections(self):
        """Update ExtraSelections for cursors with text selections"""
        selections = []

        for state in self.editor.secondary_cursors:
            if state.hasSelection():
                # Create ExtraSelection for the text selection
                selection = QtWidgets.QTextEdit.ExtraSelection()
                fmt = QtGui.QTextCharFormat()
                fmt.setBackground(self.selection_color.lighter(150))
                selection.format = fmt
                selection.cursor = state.build_cursor(self.editor.document())
                selections.append(selection)

        # Check if primary cursor has a selection (only in multi-cursor mode)
        if self.editor.secondary_cursors:
            primary = self.editor.get_primary_cursor()
            if primary.hasSelection():
                selection = QtWidgets.QTextEdit.ExtraSelection()
                fmt = QtGui.QTextCharFormat()
                fmt.setBackground(self.selection_color.lighter(150))
                selection.format = fmt
                selection.cursor = primary.build_cursor(self.editor.document())
                selections.append(selection)

        self.editor.set_selections("multi_cursor", selections)

    def clear_visual(self):
        """Public method called by CodeEditor when exiting multi-cursor mode"""
        self.editor.clear_selections("multi_cursor")
        self.editor.viewport().update()

    def paintEvent(self, e: QtGui.QPaintEvent, painter: QtGui.QPainter):
        """Paint thin cursor lines for all cursors without selections"""
        if not self._blink_state:
            return
        painter.save()
        try:
            cursor = QtGui.QTextCursor(self.editor.document())

            # Draw secondary cursors (if in multi-cursor mode)
            for state in self.editor.secondary_cursors:
                if not state.hasSelection():
                    self._draw_cursor_at_position(
                        painter, cursor, state.position, self.secondary_cursor_color
                    )

            # Always draw primary cursor
            primary = self.editor.get_primary_cursor()
            if not primary.hasSelection():
                self._draw_cursor_at_position(
                    painter, cursor, primary.position, self.primary_cursor_color
                )
        finally:
            painter.restore()

    def _update_blink(self):
        self._blink_state = not self._blink_state
        self.editor.viewport().repaint()

    def _draw_cursor_at_position(
        self,
        painter: QtGui.QPainter,
        cursor: QtGui.QTextCursor,
        position: int,
        color: QtGui.QColor,
    ):
        """Draw a thin cursor line at the specified document position

        Args:
            painter: The QPainter to draw with
            position: UTF-16 character position in the document
            color: Color to draw the cursor
        """
        # Get the cursor rectangle for this position
        cursor.setPosition(position)

        # Get the cursor rect in viewport coordinates
        cursor_rect = self.editor.cursorRect(cursor)

        # Check if cursor is visible in viewport
        viewport_rect = self.editor.viewport().rect()
        if not viewport_rect.intersects(cursor_rect):
            return

        # Draw a thin vertical line
        pen = QtGui.QPen(color)
        pen.setWidth(self.cursor_width)
        painter.setPen(pen)

        x = cursor_rect.left()
        y_top = cursor_rect.top()
        y_bottom = cursor_rect.bottom()

        painter.drawLine(QtCore.QPoint(x, y_top), QtCore.QPoint(x, y_bottom))

    def remove(self):
        """Clean up when behavior is removed"""
        self.editor.clear_selections("multi_cursor")
