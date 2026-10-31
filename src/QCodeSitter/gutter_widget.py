from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from .code_editor import CodeEditor


class GutterWidget(QtWidgets.QWidget):
    """Handle the painting of a Line Number column"""

    # TODO: relative line numbers
    def __init__(self, name: str, editor: CodeEditor):
        super().__init__(editor)
        self.editor: CodeEditor = editor
        self.name = name
        self.editor.gutterResize.connect(self.set_gutter_geo)
        self.editor.gutterWidths[self.name] = 0
        self.editor.gutterOrder.append(self.name)

    def sizeHint(self):
        return QtCore.QSize(self.width_hint(), 0)

    def width_hint(self):
        raise NotImplementedError("width_hint must be defined")

    def update_width(self):
        # This gets called on every full-viewport update, so skip it if nothing changed
        width = self.width_hint()
        if self.editor.gutterWidths[self.name] == width:
            return
        self.editor.gutterWidths[self.name] = width
        self.editor.updateGutter()

    def clear_width(self):
        # Preserve other margins when removing line numbers
        self.editor.gutterWidths[self.name] = 0
        self.editor.updateGutter()

    def gutter_offset(self):
        left = 0
        for name in self.editor.gutterOrder:
            if name == self.name:
                break
            left += self.editor.gutterWidths[name]
        return left

    def set_gutter_geo(self):
        """Handle resize events to update line number area geometry"""
        cr = self.editor.contentsRect()
        left_off = self.gutter_offset()
        self.setGeometry(
            QtCore.QRect(
                cr.left() + left_off,
                cr.top(),
                self.width_hint(),
                cr.height(),
            )
        )

    @QtCore.Slot(QtCore.QRect, int)
    def update_gutter(self, rect: QtCore.QRect, dy: int):
        if dy:
            self.scroll(0, dy)
        else:
            # Repaint the rows of the gutter that changed in the viewport
            self.update(0, rect.y(), self.width(), rect.height())

        if rect.contains(self.editor.viewport().rect()):
            self.update_width()

    def paintEvent(self, event: QtGui.QPaintEvent):
        raise NotImplementedError("paintEvent must be defined")
