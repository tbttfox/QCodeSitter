from __future__ import annotations
from Qt.QtCore import QTimer, Qt
from Qt.QtGui import QKeyEvent
from Qt.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QApplication
from dataclasses import dataclass
from tree_sitter import Node, Point, Tree
from typing import Optional, TYPE_CHECKING, Collection, Type, TypeVar
from . import Behavior, HasKeyPress
from ..utils import hk

from .providers import Provider


if TYPE_CHECKING:
    from ..line_editor import CodeEditor

COMPLETION_FORMAT = "{text} ({kind})"

T_Provider = TypeVar("T_Provider", bound=Provider)

@dataclass
class IdentifierInfo:
    """Information about an identifier in the source code"""

    text: str
    kind: str  # "function", "class", "variable", etc.


@dataclass
class Completion:
    """A single completion result"""

    text: str  # Completion text (e.g., "path")
    kind: str  # "function", "class", "variable", "module", etc.
    priority: int  # For sorting (higher = more important)

    def display(self):
        return COMPLETION_FORMAT.format(text=self.text, kind=self.kind)

    def __hash__(self):
        return hash((self.text, self.kind))


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


class TabCompletion(HasKeyPress, Behavior):
    """Orchestrates completion requests with debouncing and caching"""

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)

        #
        self.vim_completion_keys = True
        self.debounce_delay = 150

        self.setListen({"vim_completion_keys", "debounce_delay"})

        self._providers: list[Provider] = []

        self.last_tree: Optional[Tree] = None
        self._last_context: CompletionContext = CompletionContext(0, 0, "", 0, "", None)

        self.editor.cursorPositionChanged.connect(self.on_cursor_changed)

        # Debounce timer to avoid triggering on every keystroke
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.do_completion)

        self.completion_popup: CompletionPopup = CompletionPopup(self.editor)

        # Initial cache population
        if editor.tree_manager.tree:
            self.last_tree = editor.tree_manager.tree
        self.updateAll()

        from .providers.identifiers import IdentifierProvider
        self._providers.append(IdentifierProvider(self))

    def addProvider(self, providercls: Type[T_Provider]) -> T_Provider:
        ret = providercls(self)
        self._providers.append(ret)
        return ret

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
                self.debounce_timer.start(self.debounce_delay)

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
        if not (context.prefix[0].isalpha() or context.prefix[0] == "_"):
            return False

        return True

    def do_completion(self):
        """Actually perform completion (called after debounce timer expires)"""
        if self.editor.tree_manager.tree:
            self.last_tree = self.editor.tree_manager.tree

        context = self._extract_context()

        # Verify we should still trigger (context might have changed during debounce)
        if not self._should_trigger(context):
            self.completion_popup.hide()
            return

        # If we're in the same completion location, just update the filter
        if (
            context.line_num == self._last_context.line_num
            and context.start == self._last_context.start
        ):
            self.completion_popup.update_filter(context.prefix)
            self._last_context = context
            return

        # Get completions from providers
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
            prefix = prefix[last_dot + 1 :]

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
            self.completion_popup.offset_current(-1)
            return True
        elif event.key() == Qt.Key_Down:
            self.completion_popup.offset_current(1)
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
                self.completion_popup.offset_current(-1)
                return True
            elif hotkey == hk(Qt.Key_N, Qt.KeyboardModifier.ControlModifier):
                self.completion_popup.offset_current(1)
                return True

        return False
