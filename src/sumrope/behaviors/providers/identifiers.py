from __future__ import annotations
from Qt.QtCore import Qt
from Qt.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QApplication
from tree_sitter import Query, QueryCursor
from typing import Optional, Collection, TYPE_CHECKING
from ..tab_completion import Completion, TabCompletion
from . import Provider

if TYPE_CHECKING:
    from ...line_editor import CodeEditor


class CompletionPopup(QListWidget):
    """Popup widget showing completion suggestions"""

    def __init__(self, parent: CodeEditor):
        super().__init__(parent)
        self.editor = parent
        self.all_completions: list[Completion] = []
        self.current_prefix: str = ""

        # Window flags for popup behavior
        # Use Qt.Tool instead of Qt.Popup to allow editor to continue receiving events
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        # Set attribute to hide from taskbar
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Styling
        '''
        self.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                color: #dcdcdc;
                border: 1px solid #555;
                font-family: Consolas, Monaco, monospace;
                font-size: 10pt;
            }
            QListWidget::item {
                padding: 4px 8px;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
        """)
        '''

        # Size constraints
        self.setMinimumWidth(200)
        self.setMaximumWidth(500)
        self.setMaximumHeight(300)

        # Scrolling
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._min_width = 200
        self._max_width = 500
        self._min_height = 20
        self._max_height = 300

    def show_completions(self, completions: Collection[Completion], prefix: str):
        """Show completions with the given prefix

        Args:
            completions: List of Completion objects to show
            prefix: The current prefix being completed
        """
        self.all_completions = sorted(
            completions, key=lambda c: (-c.priority, c.text.lower())
        )
        self.update_filter(prefix)

    def update_filter(self, new_prefix: str):
        """Update visible completions based on new prefix

        This is more efficient than re-querying providers.

        Args:
            new_prefix: The new prefix to filter by
        """
        self.current_prefix = new_prefix
        self._update_items()
        self.update_shown()

    def update_shown(self):
        if self.count() > 0:
            self.setCurrentRow(0)
            self._position_at_cursor()
            self.show()
            # Don't steal focus from editor
            self.setFocusPolicy(Qt.NoFocus)
        else:
            self.hide()

    def _update_items(self):
        """Update the list widget items based on current prefix"""
        prefix_lower = self.current_prefix.lower()

        # If we already have items, try to update visibility instead of rebuilding
        if self.count() > 0:
            visible_count = 0
            for i in range(self.count()):
                item = self.item(i)
                comp: Completion = item.data(Qt.UserRole)
                should_show = (
                    comp.text.lower().startswith(prefix_lower)
                    and comp.text != self.current_prefix
                )
                item.setHidden(not should_show)
                if should_show:
                    visible_count += 1

            # If visible count matches, we're done
            if visible_count > 0:
                return

        # Otherwise, rebuild the list (first time or no matches with current items)
        self.clear()
        for comp in self.all_completions:
            if (
                comp.text.lower().startswith(prefix_lower)
                and comp.text != self.current_prefix
            ):
                item = QListWidgetItem(comp.display())
                item.setData(Qt.UserRole, comp)
                self.addItem(item)

    def _position_at_cursor(self):
        """Position the popup at the editor's cursor"""
        cursor = self.editor.textCursor()
        cursor_rect = self.editor.cursorRect(cursor)

        # Position below cursor line
        popup_pos = self.editor.mapToGlobal(cursor_rect.bottomLeft())

        # Adjust width based on content
        if self.count() > 0:
            # Calculate optimal width from items
            max_width = self._min_width
            for i in range(min(self.count(), 20)):  # Check first 20 items
                item_width = (
                    self.fontMetrics().horizontalAdvance(self.item(i).text()) + 30
                )
                max_width = max(max_width, item_width)

            self.setFixedWidth(min(max_width, self._max_width))

        # Calculate optimal height
        row_height = self.sizeHintForRow(0) if self.count() > 0 else self._min_height
        optimal_height = min(self.count() * row_height + 4, self._max_height)
        self.setFixedHeight(optimal_height)

        # Check if popup fits below cursor, otherwise show above
        screen_geom = QApplication.desktop().availableGeometry(self.editor)

        if popup_pos.y() + self.height() > screen_geom.bottom():
            # Show above cursor
            popup_pos = self.editor.mapToGlobal(cursor_rect.topLeft())
            popup_pos.setY(popup_pos.y() - self.height())

        self.move(popup_pos)

    def accept_completion(self):
        """Accept the currently selected completion"""
        item = self.currentItem()
        if item is None:
            self.hide()
            return

        comp: Completion = item.data(Qt.UserRole)
        cursor = self.editor.textCursor()

        # Calculate how many characters to remove (the prefix length)
        prefix_len = len(self.current_prefix)

        # Remove the prefix
        for _ in range(prefix_len):
            cursor.deletePreviousChar()

        # Insert the completion text
        cursor.insertText(comp.text)

        self.editor.setTextCursor(cursor)
        self.hide()

    def offset_current(self, offset):
        current = self.currentRow()
        current = (current + offset) % self.count()
        item = self.item(current)
        self.setCurrentRow(current)
        self.scrollToItem(item)


class IdentifierProvider(Provider):
    IDENTIFIER_QUERY = """
    (function_definition name: (identifier) @function)
    (class_definition name: (identifier) @class)
    (assignment left: (identifier) @variable)
    (parameters (identifier) @parameter)
    (import_statement name: (dotted_name (identifier) @import))
    (import_from_statement name: (dotted_name (identifier) @import))
    (aliased_import name: (dotted_name (identifier) @import))
    (aliased_import alias: (identifier) @import)
    """
    # TODO: Get id queries for non-python languages from the editorOptions
    # Also, pull Providers out into their own files

    def __init__(self, tabcomplete: TabCompletion):
        super().__init__(tabcomplete)
        self.query: Optional[Query] = None

        tree = self.tabcomplete.last_tree
        if tree is None:
            return

        self.query = Query(tree.language, self.IDENTIFIER_QUERY)

    def provide(self) -> set[Completion]:
        """Extract identifiers from the document's tree"""
        tree = self.tabcomplete.last_tree
        if tree is None:
            return set()

        if self.query is None:
            self.query = Query(tree.language, self.IDENTIFIER_QUERY)

        cursor = QueryCursor(self.query)

        # Set the byte range for the query cursor
        cursor.set_byte_range(0, tree.root_node.end_byte)
        identifiers = set()

        captures = cursor.captures(tree.root_node)
        for capture_name, nodes in captures.items():
            for node in nodes:
                if node.text is None:
                    continue

                name = node.text.decode("utf-16-le")
                # Skip empty or invalid identifiers
                if name and name.isidentifier():
                    identifiers.add(
                        Completion(
                            text=name,
                            kind=capture_name,
                            priority=3,
                        )
                    )
        return identifiers
