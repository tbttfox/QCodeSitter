from __future__ import annotations

from Qt import QtCore, QtGui, QtWidgets

# QGuiApplication is not re-exported by Qt.py, so import directly
from ..qt_missing import QGuiApplication

from dataclasses import dataclass
from tree_sitter import Node, Point, Tree
from typing import Optional, TYPE_CHECKING, Collection, Type, TypeVar
from . import Behavior, HasKeyPress

from .providers import Provider


if TYPE_CHECKING:
    from ..code_editor import CodeEditor

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


class CompletionPopup(QtWidgets.QListWidget):
    """Popup widget showing completion suggestions"""

    def __init__(self, parent: CodeEditor):
        super().__init__(parent)
        self.editor = parent
        self.all_completions: list[Completion] = []
        self.current_prefix: str = ""

        # Window flags for popup behavior
        # Use Qt.WindowType.Tool instead of Qt.WindowType.Popup to allow editor to continue receiving events
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )

        # Set attribute to hide from taskbar
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Base, QtGui.QColor("#2b2b2b")
        )  # Background
        palette.setColor(
            QtGui.QPalette.ColorRole.Text, QtGui.QColor("#dcdcdc")
        )  # Text color
        palette.setColor(
            QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#094771")
        )  # Selection background
        palette.setColor(
            QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff")
        )  # Selection text
        palette.setColor(
            QtGui.QPalette.ColorRole.Window, QtGui.QColor("#2b2b2b")
        )  # Window background
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Size constraints
        self.setMinimumWidth(200)
        self.setMaximumWidth(500)
        self.setMaximumHeight(300)

        # Scrolling
        self.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
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
                comp: Completion = item.data(QtCore.Qt.ItemDataRole.UserRole)
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
                item = QtWidgets.QListWidgetItem(comp.display())
                item.setData(QtCore.Qt.ItemDataRole.UserRole, comp)
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
        # Qt 6 compatible: use screen() instead of deprecated desktop()
        screen = QGuiApplication.screenAt(
            self.editor.mapToGlobal(self.editor.rect().center())
        )
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        screen_geom = screen.availableGeometry()

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

        comp: Completion = item.data(QtCore.Qt.ItemDataRole.UserRole)
        cursor = self.editor.textCursor()

        # Calculate how many characters to remove (the prefix length)
        prefix_len = len(self.current_prefix)

        # Select the prefix and replace it with the completion text in one operation
        # Using a single operation prevents multiple tree-sitter edit notifications
        # which can cause the tree to get into an inconsistent state
        cursor.movePosition(
            cursor.MoveOperation.PreviousCharacter,
            cursor.MoveMode.KeepAnchor,
            prefix_len,
        )
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

        self.vim_completion_keys = True
        self.debounce_delay = 150

        self.setListen({"vim_completion_keys", "debounce_delay"})

        self._providers: list[Provider] = []

        self.last_tree: Optional[Tree] = None
        self._last_context: CompletionContext = CompletionContext(0, 0, "", 0, "", None)
        self._typing_mode: bool = False  # Track if we're in active typing session

        self.editor.cursorPositionChanged.connect(self.on_cursor_changed)
        self.editor.textChanged.connect(self.on_text_changed)

        # Debounce timer to avoid triggering on every keystroke
        self.debounce_timer = QtCore.QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.do_completion)

        self.completion_popup: CompletionPopup = CompletionPopup(self.editor)

        # Initial cache population
        if editor.tree_manager.tree:
            self.last_tree = editor.tree_manager.tree
        self.updateAll()

    def addProvider(self, providercls: Type[T_Provider]) -> T_Provider:
        ret = providercls(self)
        self._providers.append(ret)
        return ret

    def on_text_changed(self):
        """Called when text changes - indicates typing is happening"""
        self._typing_mode = True

    def on_cursor_changed(self):
        """Called when cursor position changes (connected to cursorPositionChanged signal)"""
        context = self._extract_context()
        if not self._should_trigger(context):
            # Hide popup if trigger conditions not met
            if self.completion_popup.isVisible():
                self.completion_popup.hide()
            # Reset typing mode when conditions not met
            self._typing_mode = False
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
            elif self._typing_mode:
                # Only auto-show popup if we're in typing mode (not just clicking around)
                # Cancel any pending completion
                self.debounce_timer.stop()
                # Start new debounce timer (150ms delay)
                self.debounce_timer.start(self.debounce_delay)

            # Reset typing mode flag after handling
            self._typing_mode = False

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

    def acceptItem(self):
        if not self.completion_popup.isVisible():
            return False
        if self.completion_popup.currentItem():
            self.completion_popup.accept_completion()
        return True

    def offset_up(self):
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.offset_current(-1)
        return True

    def offset_down(self):
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.offset_current(1)
        return True

    def hide_and_accept(self):
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.hide()
        return True

    def hide_and_deny(self):
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.hide()
        return False

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> bool:
        KEY = QtCore.Qt.Key
        key = event.key()
        if key == KEY.Key_Return:
            return self.acceptItem()
        elif key == KEY.Key_Tab:
            return self.acceptItem()
        elif key == KEY.Key_Up:
            return self.offset_up()
        elif key == KEY.Key_Down:
            return self.offset_down()
        elif key == KEY.Key_Escape:
            return self.hide_and_accept()
        elif key == KEY.Key_Backspace:
            return self.hide_and_deny()

        if self.vim_completion_keys:
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                if key == KEY.Key_Y:
                    return self.acceptItem()
                elif key == KEY.Key_P:
                    return self.offset_up()
                elif key == KEY.Key_N:
                    return self.offset_down()

        return False
