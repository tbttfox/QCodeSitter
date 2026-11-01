"""The columns beside the editor viewport, like line numbers and fold markers"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from Qt import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from .code_editor import CodeEditor


class GutterLayout:
    """Lays out an editor's gutters left of its viewport, in the order they were added

    The editor owns one as `editor.gutters`, and iterating it gives the gutters
    """

    def __init__(self, editor: CodeEditor) -> None:
        self.editor = editor
        self._gutters: list[GutterWidget] = []

    def __iter__(self) -> Iterator[GutterWidget]:
        return iter(list(self._gutters))

    def add(self, gutter: GutterWidget) -> None:
        """Add a gutter to the right of the others. GutterWidget calls this"""
        gutter.reserved_width = gutter.width_hint()
        self._gutters.append(gutter)
        self.layout()

    def remove(self, gutter: GutterWidget) -> None:
        """Remove a gutter and close the gap. GutterWidget.remove calls this"""
        self._gutters.remove(gutter)
        self.layout()

    def layout(self) -> None:
        """Make room for the gutters left of the viewport, and put them there"""
        margins = self.editor.viewportMargins()
        margins.setLeft(sum(g.reserved_width for g in self._gutters))
        self.editor.setViewportMargins(margins)
        self.place()

    def place(self) -> None:
        """Fit the gutters to the editor's height, side by side"""
        rect = self.editor.contentsRect()
        left = rect.left()
        for gutter in self._gutters:
            gutter.setGeometry(left, rect.top(), gutter.reserved_width, rect.height())
            left += gutter.reserved_width

    def update(self) -> None:
        """Repaint every gutter, like after lines are hidden or shown"""
        for gutter in self._gutters:
            gutter.update()


class GutterWidget(QtWidgets.QWidget):
    """Base class for a column beside the editor viewport, like line numbers

    A gutter adds itself to the editor's GutterLayout when it is made.
    Subclasses define `width_hint` and `paintEvent`, and call `remove` to take
    the gutter away.
    """

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.editor: CodeEditor = editor
        self.fg_color = QtGui.QColor()
        self.bg_color = QtGui.QColor()
        # The width the editor has made room for
        self.reserved_width = 0
        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_gutter)
        self.editor.gutters.add(self)
        if self.editor.isVisible():
            self.show()

    def set_gutter_colors(self, fg: QtGui.QColor, bg: QtGui.QColor) -> None:
        self.fg_color = fg
        self.bg_color = bg
        self.update()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self.width_hint(), 0)

    def width_hint(self) -> int:
        raise NotImplementedError("width_hint must be defined")

    def update_width(self) -> None:
        # This gets called on every full-viewport update, so skip it if nothing changed
        width = self.width_hint()
        if self.reserved_width != width:
            self.reserved_width = width
            self.editor.gutters.layout()

    def remove(self) -> None:
        """Take the gutter out of the editor, and give its space back"""
        self.editor.blockCountChanged.disconnect(self.update_width)
        self.editor.updateRequest.disconnect(self.update_gutter)
        self.editor.gutters.remove(self)
        self.deleteLater()

    @QtCore.Slot(QtCore.QRect, int)
    def update_gutter(self, rect: QtCore.QRect, dy: int) -> None:
        if dy:
            self.scroll(0, dy)
        else:
            # Repaint the rows of the gutter that changed in the viewport
            self.update(0, rect.y(), self.width(), rect.height())

        if rect.contains(self.editor.viewport().rect()):
            self.update_width()

    def visible_blocks(
        self, bottom_limit: float | None = None
    ) -> Iterator[tuple[QtGui.QTextBlock, float, float]]:
        """Yield each visible block with its top and bottom in gutter coordinates

        Args:
            bottom_limit: Stop after the block that reaches past this y position
        """
        block = self.editor.firstVisibleBlock()
        top = (
            self.editor.blockBoundingGeometry(block)
            .translated(self.editor.contentOffset())
            .top()
        )
        while block.isValid() and (bottom_limit is None or top <= bottom_limit):
            bottom = top + self.editor.blockBoundingRect(block).height()
            if block.isVisible():
                yield block, top, bottom
            block = block.next()
            top = bottom

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        raise NotImplementedError("paintEvent must be defined")
