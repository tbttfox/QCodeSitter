from __future__ import annotations
from . import Behavior, HasKeyPress
from ..utils import hk
from typing import TYPE_CHECKING
from Qt import QtGui, QtWidgets, QtCore
import re

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


WORDS = re.compile("[A-Za-z0-9_]+")


class TabCompletion(HasKeyPress, Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.updateAll()
        self.display_limit = 50
        self.providers = []
        self.all_completions = ["this", "that", "theother"]

        # Create autocomplete widget with proper styling
        self.autocomplete_list = QtWidgets.QListWidget()
        self.autocomplete_list.setWindowFlags(QtCore.Qt.ToolTip)
        self.autocomplete_list.setFocusPolicy(QtCore.Qt.NoFocus)
        self.autocomplete_list.setMouseTracking(True)

        # Style the autocomplete list
        self.autocomplete_list.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                color: #dcdcdc;
                border: 1px solid #555;
                outline: none;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #404040;
            }
            QListWidget::item:hover {
                background-color: #383838;
            }
        """)

        self.autocomplete_list.itemClicked.connect(self.insert_completion)
        self.autocomplete_list.hide()

    def get_word_start(self, linetxt, cursorcol):
        """Find the start position of the current word, handling whitespace"""
        if cursorcol == 0:
            return 0
        pretxt_rev = linetxt[cursorcol - 1 :: -1]
        match = WORDS.match(pretxt_rev)
        if match is None:
            return 0
        return match.end()

    def filter_completions_local(self):
        """Filter the cached completions locally based on current prefix"""
        cursor = self.editor.textCursor()
        block_text = cursor.block().text()
        col = cursor.columnNumber()

        # Get current prefix from the word start
        word_start = self.get_word_start(block_text, col)
        current_prefix = block_text[word_start:col]
        if not current_prefix:
            if word_start == 0:
                self.autocomplete_list.hide()
                return
            filtered = self.all_completions[:]
        else:
            filtered = [
                c for c in self.all_completions if c["name"].startswith(current_prefix)
            ]

        if not filtered:
            self.autocomplete_list.hide()
            return

        # Update the list
        self.autocomplete_list.clear()
        for comp in filtered[: self.display_limit]:
            self.autocomplete_list.addItem(comp["name"])
            # Store the full completion data in item's user data for later retrieval
            item = self.autocomplete_list.item(self.autocomplete_list.count() - 1)
            item.setData(QtCore.Qt.UserRole, comp)

        # Position and show
        cursor_rect = self.editor.cursorRect(cursor)
        pos = self.editor.mapToGlobal(cursor_rect.bottomRight())

        # TODO: Get the sizes better based on font metrics
        self.autocomplete_list.move(pos)
        self.autocomplete_list.setFixedWidth(300)
        self.autocomplete_list.setFixedHeight(min(400, len(filtered) * 25))
        self.autocomplete_list.setCurrentRow(0)
        self.autocomplete_list.show()
        self.autocomplete_list.raise_()

    def insert_completion(self, item):
        cursor = self.editor.textCursor()
        text = cursor.block().text()
        col = cursor.columnNumber()

        # Find word start
        word_start = self.get_word_start(text, col)

        cursor.movePosition(
            QtGui.QTextCursor.Left, QtGui.QTextCursor.MoveAnchor, col - word_start
        )
        cursor.movePosition(
            QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, col - word_start
        )
        cursor.insertText(item.text())

        self.autocomplete_list.hide()

    def keyPressEvent(self, event: QtGui.QKeyEvent, hotkey: str):
        if self.autocomplete_list.isVisible():
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Tab) or hotkey == hk(
                QtCore.Qt.Key_Y, QtCore.Qt.KeyboardModifier.ControlModifier
            ):
                if self.autocomplete_list.currentItem():
                    self.insert_completion(self.autocomplete_list.currentItem())
                return True
            elif event.key() == QtCore.Qt.Key_Escape:
                self.autocomplete_list.hide()
                return True
            elif event.key() == QtCore.Qt.Key_Up or hotkey == hk(
                QtCore.Qt.Key_P, QtCore.Qt.KeyboardModifier.ControlModifier
            ):
                current = self.autocomplete_list.currentRow()
                if current > 0:
                    self.autocomplete_list.setCurrentRow(current - 1)
                return True
            elif event.key() == QtCore.Qt.Key_Down or hotkey == hk(
                QtCore.Qt.Key_N, QtCore.Qt.KeyboardModifier.ControlModifier
            ):
                current = self.autocomplete_list.currentRow()
                if current < self.autocomplete_list.count() - 1:
                    self.autocomplete_list.setCurrentRow(current + 1)
                return True
            elif event.key() in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Escape):
                self.autocomplete_list.hide()
                return True
        return False
