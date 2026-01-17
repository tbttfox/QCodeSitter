from __future__ import annotations
from . import HasPaint, Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore, QtWidgets

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class MultiCursorPaint(HasPaint, Behavior):
    """Behavior that renders multi-cursors with custom painting

    This behavior handles rendering of both the primary cursor and secondary
    cursors when in multi-cursor mode. It uses:
    - Custom thin cursor lines for cursor positions (rendered via painting)
    - ExtraSelections for text selections (rendered via Qt's selection mechanism)
    """

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen(set())

        # Cursor appearance
        self.cursor_width = 2
        self.primary_cursor_color = QtGui.QColor(255, 255, 255, 255)  # White
        self.secondary_cursor_color = QtGui.QColor(180, 180, 180, 200)  # Gray
        self.selection_color = QtGui.QColor(180, 180, 180, 200)  # Gray for selections

        # Blinking state for cursors
        self._blink_visible = True
        self._blink_timer = QtCore.QTimer()
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start(500)  # Blink every 500ms

    def _toggle_blink(self):
        """Toggle cursor blink state"""
        self._blink_visible = not self._blink_visible
        self.editor.viewport().update()

    def update_visual(self):
        """Public method called by CodeEditor when cursors change"""
        # Reset blink to visible when cursors change
        self._blink_visible = True
        self._blink_timer.start()

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
        self._blink_timer.stop()
        self.editor.clear_selections("multi_cursor")
        self.editor.viewport().update()

    def paintEvent(self, e: QtGui.QPaintEvent, painter: QtGui.QPainter):
        """Paint thin cursor lines for all cursors without selections"""
        # Only paint cursors if we're in multi-cursor mode or if we should show primary
        if not self.editor.secondary_cursors:
            return

        # Only draw cursors if blink is visible
        if not self._blink_visible:
            return

        painter.save()
        try:
            cursor = QtGui.QTextCursor(self.editor.document())
            # Draw secondary cursors
            for state in self.editor.secondary_cursors:
                if not state.hasSelection():
                    self._draw_cursor_at_position(
                        painter, cursor, state.position, self.secondary_cursor_color
                    )

            # Draw primary cursor in multi-cursor mode
            primary = self.editor.get_primary_cursor()
            if not primary.hasSelection():
                self._draw_cursor_at_position(
                    painter, cursor, primary.position, self.primary_cursor_color
                )
        finally:
            painter.restore()

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
        self._blink_timer.stop()
        self.editor.clear_selections("multi_cursor")
