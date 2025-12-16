from __future__ import annotations
from Qt.QtWidgets import QPlainTextEdit
from Qt.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPalette,
    QResizeEvent,
    QTextBlock,
    QTextCursor,
)
from typing import Callable, Optional, Collection, Type, TypeVar
from tree_sitter import Language, Point
from Qt import QtCore

from .line_tracker import TrackedDocument
from .behaviors import Behavior, HasKeyPress, HasResize
from .tree_manager import TreeManager
from .syntax_analyzer import SyntaxAnalyzer
from .editor_options import EditorOptions
from .selection_manager import SelectionManager
from .multi_cursor_manager import MultiCursorManager
from .utils import hk

T_Behavior = TypeVar("T_Behavior", bound=Behavior)


class CodeEditor(QPlainTextEdit):
    def __init__(
        self,
        options: EditorOptions,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._doc: TrackedDocument = TrackedDocument()
        self.setDocument(self._doc)

        self.options = options
        self._ts_prediction: dict[int, QTextBlock] = {}

        self.tree_manager: TreeManager
        self.syntax_analyzer: SyntaxAnalyzer
        self.selection_manager: SelectionManager = SelectionManager(self)
        self.multi_cursor_manager: MultiCursorManager = MultiCursorManager(self)

        # Hotkeys
        self.hotkeys: dict[str, Callable[[QTextCursor], bool]] = {}

        # Register Ctrl+D for multi-cursor next occurrence
        self.hotkeys[hk(QtCore.Qt.Key.Key_D, QtCore.Qt.KeyboardModifier.ControlModifier)] = (
            lambda cursor: self.multi_cursor_manager.add_next_occurrence()
        )

        # Register Ctrl+Alt+Up to add cursor above
        self.hotkeys[hk(
            QtCore.Qt.Key.Key_Up,
            QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.AltModifier
        )] = lambda cursor: self.multi_cursor_manager.add_cursor_above()

        # Register Ctrl+Alt+Down to add cursor below
        self.hotkeys[hk(
            QtCore.Qt.Key.Key_Down,
            QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.AltModifier
        )] = lambda cursor: self.multi_cursor_manager.add_cursor_below()

        # Register Ctrl+Shift+L to add cursor to each line in selection
        self.hotkeys[hk(
            QtCore.Qt.Key.Key_L,
            QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier
        )] = lambda cursor: self.multi_cursor_manager.add_cursors_to_line_ends()

        self._behaviors: list[Behavior] = []

        self.options.optionsUpdated.connect(self.updateOptions)
        self.updateOptions(list(self.options.keys()))

    def updateOptions(self, keylist: Collection[str]):
        keys = set(keylist)
        if "font" in keys:
            self.setFont(self.options["font"])
        if "language" in keys:
            self.setLanguage(self.options["language"])
        if "colors" in keys:
            self.setColors(self.options["colors"])

    def setColors(self, colors: dict[str, str]):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(colors["bg"]))  # Background
        palette.setColor(QPalette.Window, QColor(colors["bg"]))  # Window background
        palette.setColor(QPalette.Text, QColor(colors["fg"]))  # Window background
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def setLanguage(self, lang: Language):
        self.tree_manager = TreeManager(lang, self._treesitter_source_callback)
        self.syntax_analyzer = SyntaxAnalyzer(self.tree_manager, self._doc)
        self._doc.byteContentsChange.connect(self.updateTree)

    def updateTree(
        self,
        start_byte: int,
        old_end_byte: int,
        new_end_byte: int,
        start_point: Point,
        old_end_point: Point,
        new_end_point: Point,
    ):
        self.tree_manager.update(
            start_byte,
            old_end_byte,
            new_end_byte,
            start_point,
            old_end_point,
            new_end_point,
        )
        #print(str(self.tree_manager.tree.root_node))

    def addBehavior(
        self, behaviorCls: Type[T_Behavior]
    ) -> tuple[Optional[T_Behavior], T_Behavior]:
        """Set the given behavior to the class. If a behavior of the given type already exists, remove it
        Return both the old and newly instantiated behaviors.
        """
        old_bh = self.removeBehavior(behaviorCls)
        behavior = behaviorCls(self)
        self._behaviors.append(behavior)
        return old_bh, behavior

    def removeBehavior(self, behaviorCls: Type[T_Behavior]) -> Optional[T_Behavior]:
        """Remove all existing behaviors of the given type"""
        ridxs = []
        for i, bh in enumerate(self._behaviors):
            if type(bh) is behaviorCls:
                ridxs.append(i)
        torem = [self._behaviors.pop(i) for i in reversed(ridxs)]
        for rem in torem:
            rem.remove()
        if not torem:
            return None
        if len(torem) > 1:
            print("Warning: Multiple behaviors of the same type found to remove")
        return torem[0]

    def getBehavior(self, behaviorCls: Type[T_Behavior]) -> Optional[T_Behavior]:
        for bh in self._behaviors:
            if type(bh) is behaviorCls:
                return bh
        return None

    def document(self) -> TrackedDocument:
        doc = super().document()
        if not isinstance(doc, TrackedDocument):
            raise ValueError("This syntax highlighter only works with TrackedDocument")
        return doc

    def _treesitter_source_callback(self, byte_offset: int, ts_point: Point) -> bytes:
        """Provide source bytes to tree-sitter parser

        A callback for efficient access to the underlying UTF-16LE encoded data

        Args:
            byte_offset: The byte offset in UTF-16LE encoding where data is requested
            ts_point: The (row, column) point in code units where data is requested

        Returns:
            UTF-16LE encoded bytes from the requested position to end of document
        """
        # Clear cache at the start of each parse (when row 0 is requested)
        # This ensures we don't use stale block references after document edits
        if ts_point.row == 0:
            self._ts_prediction = {}

        curblock: Optional[QTextBlock] = self._ts_prediction.get(ts_point.row)
        if curblock is None:
            try:
                curblock = self.document().findBlockByNumber(ts_point.row)
            except IndexError:
                self._ts_prediction = {}
                return b""

        # Check if block is valid (can be invalid after undo)
        if not curblock.isValid():
            self._ts_prediction = {}
            return b""

        self._ts_prediction[ts_point.row] = curblock
        nxt = curblock.next()
        self._ts_prediction[ts_point.row + 1] = nxt
        suffix = "\n" if nxt.isValid() else ""
        linetext = curblock.text() + suffix

        # Return UTF-16LE encoded bytes starting from the column offset
        # When using encoding='utf16', ts_point.column is in BYTES, not code units
        # So we need to divide by 2 to get the character position
        char_col = ts_point.column // 2
        return linetext[char_col:].encode("utf-16-le")

    def keyPressEvent(self, event: QKeyEvent):
        # Check if multi-cursor manager wants to handle this
        if self.multi_cursor_manager.is_active():
            if self.multi_cursor_manager.handle_key_event(event):
                return

        key = event.key()
        modifiers = event.modifiers()
        hotkey = hk(key, modifiers)

        accepted = False
        for behavior in self._behaviors:
            if not isinstance(behavior, HasKeyPress):
                continue
            accepted = behavior.keyPressEvent(event, hotkey)
            if accepted:
                return

        func = self.hotkeys.get(hotkey)
        if func is not None:
            cursor = self.textCursor()
            if func(cursor):
                # Don't restore cursor if we're in multi-cursor mode
                # (multi-cursor functions manage their own cursor positions)
                if not self.multi_cursor_manager.is_active():
                    self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events"""
        # Check for Alt+Click to add cursor
        if event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
            # Get the position at the click location
            cursor = self.cursorForPosition(event.pos())
            position = cursor.position()
            self.multi_cursor_manager.add_cursor_at_position(position)
            event.accept()
            return

        # Exit multi-cursor mode on normal click
        if self.multi_cursor_manager.is_active():
            self.multi_cursor_manager.exit_multi_cursor_mode()
        super().mousePressEvent(event)

    def resizeEvent(self, e: QResizeEvent):
        """Handle resize events to update line number area geometry"""
        super().resizeEvent(e)

        for behavior in self._behaviors:
            if isinstance(behavior, HasResize):
                behavior.resizeEvent(e)

    def expandCursorToLines(self, cursor: QTextCursor):
        """Expand a cursor selection to whole lines
        If there is no selection, expand to the current line
        """
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
        else:
            start = cursor.position()
            end = start

        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)

    def updateAllLines(self, newtxt: str):
        """Update the entire text range to the given text"""
        cursor = self.textCursor()
        numchars = self.document().characterCount()
        cursor.setPosition(0)
        cursor.setPosition(numchars, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(newtxt)
