from __future__ import annotations
from Qt.QtCore import QTimer, Qt
from Qt.QtGui import QKeyEvent
from Qt.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QApplication
from dataclasses import dataclass
from tree_sitter import Node, Point, Tree, Query, QueryCursor
from typing import Optional, TYPE_CHECKING, Collection
from . import Behavior, HasKeyPress
from ..utils import hk


if TYPE_CHECKING:
    from .line_editor import CodeEditor


@dataclass
class IdentifierInfo:
    """Information about an identifier in the source code"""

    text: str
    kind: str  # "function", "class", "variable", etc.


COMPLETION_FORMAT = "{text} ({kind})"


@dataclass
class Completion:
    """A single completion result"""

    text: str  # Completion text (e.g., "path")
    kind: str  # "function", "class", "variable", "module", etc.
    priority: int  # For sorting (higher = more important)

    def display(self):
        return COMPLETION_FORMAT.format(
            text=self.text, kind=self.kind, priority=self.priority
        )

    def __hash__(self):
        return hash((self.text, self.kind, self.priority))


@dataclass
class CompletionContext:
    """Context information for completion request"""

    line_num: int  # 0-indexed line number
    char_col: int  # Character column in line
    prefix: str  # Text being completed (e.g., "os.pat")
    start: int  # The start index of the prefix
    full_line: str  # Complete line text
    node: Optional[Node]  # Tree-sitter node at cursor


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
        self.updateShown()

    def updateShown(self):
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
        self.clear()

        prefix_lower = self.current_prefix.lower()
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

    def offsetCurrent(self, offset):
        current = self.currentRow()
        current = (current + offset) % self.count()
        item = self.item(current)
        self.setCurrentRow(current)
        self.scrollToItem(item)


class Provider:
    def provide(self) -> set[Completion]:
        raise NotImplementedError("A Provider must override the .provide() method")


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
        self.tabcomplete = tabcomplete
        self.query: Optional[Query] = None

        tree = self.tabcomplete.last_tree
        if tree is None:
            return

        self.query = Query(tree.language, self.IDENTIFIER_QUERY)

    def provide(self) -> set[Completion]:
        """Extract identifiers from a specific byte range in the tree

        Args:
            tree: The tree-sitter Tree to extract from
            start_byte: The start byte for the range. Defaults to 0
            end_byte: The end byte of the range. Defatuls to -1 (the end of the range)
        """
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


class TabCompletion(HasKeyPress, Behavior):
    """Orchestrates completion requests with debouncing and caching"""

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)

        self._providers: list[Provider] = []

        self.last_tree: Optional[Tree] = None
        self._last_context: CompletionContext = CompletionContext(0, 0, "", 0, "", None)

        self.editor.cursorPositionChanged.connect(self.on_cursor_changed)

        # Debounce timer to avoid triggering on every keystroke
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.do_completion)

        self.completion_popup: CompletionPopup = CompletionPopup(self.editor)
        self.vim_completion_keys = True

        # Initial cache population
        if editor.tree_manager.tree:
            self.last_tree = editor.tree_manager.tree
        self.updateAll()

        self._providers.append(IdentifierProvider(self))

    def on_cursor_changed(self):
        """Called when cursor position changes (connected to cursorPositionChanged signal)"""
        context = self._extract_context()
        if not self._should_trigger(context):
            # Hide popup if trigger conditions not met
            if self.completion_popup.isVisible():
                self.completion_popup.hide()
        else:
            # If popup is already visible and we're still in the same completion context,
            # update the filter immediately without debouncing
            if (
                self.completion_popup.isVisible()
                and context.line_num == self._last_context.line_num
                and context.start == self._last_context.start
            ):
                self.completion_popup.update_filter(context.prefix)
                self._last_context = context
            else:
                # Cancel any pending completion
                self.debounce_timer.stop()
                # Start new debounce timer (150ms delay)
                self.debounce_timer.start(150)

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
        if not (context.prefix[0].isalpha() or context.prefix[0] == '_'):
            return False

        return True

    def do_completion(self):
        """Actually perform completion (called after debounce timer expires)"""
        if self.editor.tree_manager.tree:
            self.last_tree = self.editor.tree_manager.tree

        context = self._extract_context()
        if (
            context.line_num == self._last_context.line_num
            and context.start == self._last_context.start
        ):
            self.completion_popup.update_filter(context.prefix)
            return

        # Get completions from identifier cache
        completions = set()
        for pr in self._providers:
            completions |= pr.provide()

        # Show popup with completions
        if completions:
            self.completion_popup.show_completions(completions, context.prefix)
        else:
            self.completion_popup.hide()

        self._last_context = context

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
        start, prefix = self._extract_prefix(full_line, char_col)

        # Get tree-sitter node at cursor position
        node = None
        if self.editor.tree_manager.tree:
            try:
                # With UTF-16, character column IS the code unit column
                byte_offset = self.editor.document().point_to_byte(
                    Point(line_num, char_col)
                )
                node = self.editor.tree_manager.get_node_at_point(byte_offset)
            except (IndexError, ValueError):
                pass

        return CompletionContext(
            line_num=line_num,
            start=start,
            char_col=char_col,
            prefix=prefix,
            full_line=full_line,
            node=node,
        )

    def _extract_prefix(self, line: str, col: int) -> tuple[int, str]:
        """Extract the identifier prefix before cursor

        Args:
            line: The line text
            col: Character column position

        Returns:
            The beginning index of the prefix string
            The prefix string (e.g., "fo" from "def fo|")
        """
        # Walk backwards from cursor while we have identifier chars or dots
        start = col
        while start > 0 and (line[start - 1].isidentifier() or line[start - 1] in "._"):
            start -= 1

        prefix = line[start:col]

        # If there's a dot in the prefix, only use the part after the last dot
        # This handles cases like "os.path.jo|" -> complete "jo" not "os.path.jo"
        if "." in prefix:
            last_dot = prefix.rfind(".")
            # Update start to point to the character after the last dot
            start = start + last_dot + 1
            prefix = prefix[last_dot + 1:]

        return start, prefix

    def keyPressEvent(self, event: QKeyEvent, hotkey: str):
        if not self.completion_popup.isVisible():
            if hotkey == hk(Qt.Key_Space, Qt.KeyboardModifier.ControlModifier):
                self.do_completion()
                return True
            elif event.key() == Qt.Key_Escape:
                self.do_completion()
                return True
            return False

        if event.key() in (Qt.Key_Return, Qt.Key_Tab):
            if self.completion_popup.currentItem():
                self.completion_popup.accept_completion()
            return True
        elif event.key() == Qt.Key_Up:
            self.completion_popup.offsetCurrent(-1)
            return True
        elif event.key() == Qt.Key_Down:
            self.completion_popup.offsetCurrent(1)
            return True
        elif event.key() == Qt.Key_Escape:
            self.completion_popup.hide()
            return True
        elif event.key() == Qt.Key_Backspace:
            self.completion_popup.hide()
            return False
        elif self.vim_completion_keys:
            if hotkey == hk(Qt.Key_Y, Qt.KeyboardModifier.ControlModifier):
                if self.completion_popup.currentItem():
                    self.completion_popup.accept_completion()
                return True
            elif hotkey == hk(Qt.Key_P, Qt.KeyboardModifier.ControlModifier):
                self.completion_popup.offsetCurrent(-1)
                return True
            elif hotkey == hk(Qt.Key_N, Qt.KeyboardModifier.ControlModifier):
                self.completion_popup.offsetCurrent(1)
                return True

        return False
