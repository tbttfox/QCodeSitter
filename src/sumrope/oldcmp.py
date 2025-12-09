from __future__ import annotations
from Qt.QtCore import QTimer, Qt
from Qt.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QApplication
from dataclasses import dataclass
from tree_sitter import Node, Point, Tree
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .line_editor import CodeEditor


class CompletionEngine:
    """Orchestrates completion requests with debouncing and caching"""

    def __init__(self, editor: CodeEditor):
        self.editor = editor
        self._providers = []
        self.last_tree: Optional[Tree] = None

        # Debounce timer to avoid triggering on every keystroke
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._do_completion)

        # Connect to document changes for cache updates
        editor.document().byteContentsChange.connect(self._on_document_changed)

        # Initial cache population
        if editor.tree_manager.tree:
            self.identifier_cache.extract_all(editor.tree_manager.tree)
            self.last_tree = editor.tree_manager.tree

    def on_cursor_changed(self):
        """Called when cursor position changes (connected to cursorPositionChanged signal)"""
        context = self._extract_context()

        if self._should_trigger(context):
            # Cancel any pending completion
            self.debounce_timer.stop()
            # Start new debounce timer (150ms delay)
            self.debounce_timer.start(150)
        else:
            # Hide popup if trigger conditions not met
            if self.editor.completion_popup.isVisible():
                self.editor.completion_popup.hide()

    def _should_trigger(self, context: CompletionContext) -> bool:
        """Determine if completion should be triggered for this context

        Args:
            context: The current completion context

        Returns:
            True if completion should be triggered, False otherwise
        """
        # Don't trigger in strings or comments
        if context.node and context.node.type in (
            "string",
            "comment",
            "string_start",
            "string_end",
        ):
            return False

        # Don't trigger if prefix is too short
        if len(context.prefix) < 2:
            return False

        # Don't trigger if prefix isn't a valid identifier start
        if not context.prefix[0].isidentifier():
            return False

        return True

    def _do_completion(self):
        """Actually perform completion (called after debounce timer expires)"""
        context = self._extract_context()

        # Get completions from identifier cache
        completions = self.identifier_cache.get_completions(context.prefix)

        # Show popup with completions
        if completions:
            self.editor.completion_popup.show_completions(completions, context.prefix)
        else:
            self.editor.completion_popup.hide()

    def _extract_context(self) -> CompletionContext:
        """Extract completion context from current editor state

        Returns:
            CompletionContext with cursor position, prefix, node, etc.
        """
        cursor = self.editor.textCursor()
        block = cursor.block()
        line_num = block.blockNumber()
        char_col = cursor.positionInBlock()
        full_line = block.text()

        # Extract prefix (word before cursor)
        prefix = self._extract_prefix(full_line, char_col)

        # Get tree-sitter node at cursor position
        node = None
        if self.editor.tree_manager.tree:
            try:
                # Convert character column to byte column
                byte_col = len(full_line[:char_col].encode("utf-8"))
                byte_offset = self.editor.document().point_to_byte(
                    Point(line_num, byte_col)
                )
                node = self.editor.tree_manager.get_node_at_point(byte_offset)
            except (IndexError, ValueError):
                pass

        return CompletionContext(
            line_num=line_num,
            char_col=char_col,
            prefix=prefix,
            full_line=full_line,
            node=node,
        )

    def _extract_prefix_old(self, line: str, col: int) -> str:
        """Extract the identifier prefix before cursor

        Args:
            line: The line text
            col: Character column position

        Returns:
            The prefix string (e.g., "fo" from "def fo|")
        """
        # Walk backwards from cursor while we have identifier chars
        start = col
        while start > 0 and (line[start - 1].isidentifier() or line[start - 1] in "._"):
            start -= 1

        return line[start:col]

    def _on_document_changed(self, *args):
        """Handle document changes to update identifier cache

        This is connected to byteContentsChange signal.
        We update the cache after the tree has been updated.
        """
        # Use single-shot timer to wait for tree update to complete
        QTimer.singleShot(0, self._update_cache)

    def _update_cache(self):
        """Update the identifier cache from the current tree"""
        if self.editor.tree_manager.tree is None:
            return

        # For Phase 1, just do a full re-extraction
        # Phase 2 will add incremental updates using changed_ranges
        self.identifier_cache.extract_all(self.editor.tree_manager.tree)
        self.last_tree = self.editor.tree_manager.tree


@dataclass
class CompletionContext:
    """Context information for completion request"""

    line_num: int  # 0-indexed line number
    char_col: int  # Character column in line
    prefix: str  # Text being completed (e.g., "os.pat")
    full_line: str  # Complete line text
    node: Optional[Node]  # Tree-sitter node at cursor


@dataclass
class Completion:
    """A single completion result"""

    text: str  # Completion text (e.g., "path")
    display: str  # What to show in popup (e.g., "path (module)")
    kind: str  # "function", "class", "variable", "module", etc.
    priority: int  # For sorting (higher = more important)


class CompletionPopup(QListWidget):
    """Popup widget showing completion suggestions"""

    def __init__(self, parent: "CodeEditor"):
        super().__init__(parent)
        self.editor = parent
        self.all_completions: List[Completion] = []
        self.current_prefix: str = ""

        # Window flags for popup behavior
        # Use Qt.Tool instead of Qt.Popup to allow editor to continue receiving events
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        # Set attribute to hide from taskbar
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Styling
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

        # Size constraints
        self.setMinimumWidth(200)
        self.setMaximumWidth(500)
        self.setMaximumHeight(300)

        # Scrolling
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def show_completions(self, completions: List[Completion], prefix: str):
        """Show completions with the given prefix

        Args:
            completions: List of Completion objects to show
            prefix: The current prefix being completed
        """
        self.all_completions = sorted(
            completions, key=lambda c: (-c.priority, c.text.lower())
        )
        self.current_prefix = prefix
        self._update_items()

        if self.count() > 0:
            self.setCurrentRow(0)
            self._position_at_cursor()
            self.show()
            # Don't steal focus from editor
            self.setFocusPolicy(Qt.NoFocus)
        else:
            self.hide()

    def update_filter(self, new_prefix: str):
        """Update visible completions based on new prefix

        This is more efficient than re-querying providers.

        Args:
            new_prefix: The new prefix to filter by
        """
        self.current_prefix = new_prefix
        self._update_items()

        if self.count() == 0:
            self.hide()

    def _update_items(self):
        """Update the list widget items based on current prefix"""
        self.clear()

        for comp in self.all_completions:
            if comp.text.startswith(self.current_prefix):
                item = QListWidgetItem(comp.display)
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
            max_width = 200
            for i in range(min(self.count(), 20)):  # Check first 20 items
                item_width = (
                    self.fontMetrics().horizontalAdvance(self.item(i).text()) + 30
                )
                max_width = max(max_width, item_width)

            self.setFixedWidth(min(max_width, 500))

        # Calculate optimal height
        row_height = self.sizeHintForRow(0) if self.count() > 0 else 20
        optimal_height = min(self.count() * row_height + 4, 300)
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

    def keyPressEvent(self, event):
        """Handle key presses in the popup"""
        # Let the list widget handle navigation
        super().keyPressEvent(event)

        # Update selection position after navigation
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            # Ensure selected item is visible
            if self.currentItem():
                self.scrollToItem(self.currentItem())
