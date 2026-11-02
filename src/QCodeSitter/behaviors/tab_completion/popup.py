from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from Qt import QtCore, QtGui, QtWidgets

from ...gui_colors import GuiColors, gui_color
from .types import Completion

if TYPE_CHECKING:
    from ...code_editor import CodeEditor

ROLE = QtCore.Qt.ItemDataRole.UserRole


class CompletionPopup(QtWidgets.QListWidget):
    """A list of completions shown under the cursor, without taking focus"""

    MIN_WIDTH = 200
    MAX_WIDTH = 500
    MAX_HEIGHT = 300
    # Only measure this many items when sizing the popup to its contents
    MEASURED_ITEMS = 20

    def __init__(self, parent: CodeEditor) -> None:
        super().__init__(parent)
        self.editor = parent
        self.all_completions: list[Completion] = []
        self.current_prefix: str = ""

        # A Tool window instead of a Popup lets the editor keep receiving key events
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(True)

        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)
        self.setMaximumHeight(self.MAX_HEIGHT)
        self.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def set_colors(self, colors: GuiColors) -> None:
        """Color the popup with the "menu", "fg" and "selection" gui colors"""
        palette = self.palette()
        role = QtGui.QPalette.ColorRole
        for roles, name in (
            ((role.Base, role.Window), "menu"),
            ((role.Text, role.HighlightedText), "fg"),
            ((role.Highlight,), "selection"),
        ):
            for color_role in roles:
                palette.setColor(color_role, gui_color(colors, name))
        self.setPalette(palette)

    def show_completions(
        self, completions: Collection[Completion], prefix: str
    ) -> None:
        """Show a new set of completions, filtered by the prefix"""
        self.all_completions = sorted(
            completions, key=lambda c: (-c.priority, c.text.lower())
        )
        self.update_filter(prefix)

    def update_filter(self, prefix: str) -> None:
        """Show the completions that start with a new prefix, without asking the providers"""
        self.current_prefix = prefix
        prefix_lower = prefix.lower()
        self.clear()
        for comp in self.all_completions:
            if comp.text.lower().startswith(prefix_lower) and comp.text != prefix:
                item = QtWidgets.QListWidgetItem(comp.display())
                item.setData(ROLE, comp)
                self.addItem(item)

        if self.count() == 0:
            self.hide()
            return
        self.setCurrentRow(0)
        self._position_at_cursor()
        self.show()

    def _position_at_cursor(self) -> None:
        """Size the popup to its items, and put it below the cursor, or above it
        if there isn't room on the screen"""
        widths = (
            self.fontMetrics().horizontalAdvance(self.item(i).text()) + 30
            for i in range(min(self.count(), self.MEASURED_ITEMS))
        )
        self.setFixedWidth(min(max(self.MIN_WIDTH, *widths), self.MAX_WIDTH))
        self.setFixedHeight(
            min(self.count() * self.sizeHintForRow(0) + 4, self.MAX_HEIGHT)
        )

        cursor_rect = self.editor.cursorRect(self.editor.textCursor())
        popup_pos = self.editor.mapToGlobal(cursor_rect.bottomLeft())
        screen = QtGui.QGuiApplication.screenAt(
            self.editor.mapToGlobal(self.editor.rect().center())
        )
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if popup_pos.y() + self.height() > screen.availableGeometry().bottom():
            popup_pos = self.editor.mapToGlobal(cursor_rect.topLeft())
            popup_pos.setY(popup_pos.y() - self.height())
        self.move(popup_pos)

    def selected_completion(self) -> Completion | None:
        """The selected completion, or None when nothing is selected"""
        item = self.currentItem()
        return None if item is None else item.data(ROLE)

    def offset_current(self, offset: int) -> None:
        """Move the selection by offset rows, wrapping around the ends"""
        row = (self.currentRow() + offset) % self.count()
        self.setCurrentRow(row)
        self.scrollToItem(self.item(row))
