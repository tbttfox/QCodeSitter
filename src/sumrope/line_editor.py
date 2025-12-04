from __future__ import annotations
from Qt.QtWidgets import QPlainTextEdit
from Qt.QtGui import (
    QResizeEvent,
    QTextCursor,
    QKeyEvent,
    QTextBlock,
)
from typing import Callable, Optional
from .line_tracker import TrackedDocument
from .line_highlighter import TreeSitterHighlighter
from .behaviors import Behavior, HasKeyPress, HasResize
import tree_sitter_python as tspython
from tree_sitter import Language, Point
from .hl_groups import FORMAT_SPECS
from .tree_manager import TreeManager
from .syntax_analyzer import SyntaxAnalyzer
from .utils import hk
from editor_options import EditorOptions


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
        # TODO: Update this when font changes
        self.options["font"] = self.font()
        self._ts_prediction: dict[int, QTextBlock] = {}

        self.tree_manager: TreeManager
        self.highlighter: TreeSitterHighlighter
        self.syntax_analyzer: SyntaxAnalyzer

        # Create tree manager with source callback

        lang = Language(tspython.language())
        self.setLanguage(lang)
        self.highlighter = TreeSitterHighlighter(
            self._doc, self.tree_manager, tspython.HIGHLIGHTS_QUERY, FORMAT_SPECS
        )

        # Hotkeys
        self.hotkeys: dict[str, Callable[[QTextCursor], bool]] = {}

        self._behaviors: list[Behavior] = []
        self._keyPressBehaviors: list[HasKeyPress] = []
        self._resizeBehaviors: list[HasResize] = []

    def setLanguage(self, lang: Language):
        self.tree_manager = TreeManager(lang, self._treesitter_source_callback)
        self.syntax_analyzer = SyntaxAnalyzer(self.tree_manager, self._doc)

    def addBehavior(self, behavior: Behavior):
        if isinstance(behavior, HasKeyPress):
            self._keyPressBehaviors.append(behavior)
        if isinstance(behavior, HasResize):
            self._resizeBehaviors.append(behavior)
        self._behaviors.append(behavior)

    def document(self) -> TrackedDocument:
        doc = super().document()
        if not isinstance(doc, TrackedDocument):
            raise ValueError("This syntax highlighter only works with TrackedDocument")
        return doc

    def _treesitter_source_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """Provide source bytes to tree-sitter parser

        A callback for efficient access to the underlying byte data without duplicating it
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
        suffix = b"\n" if nxt.isValid() else b""
        linebytes = curblock.text().encode() + suffix

        return linebytes[ts_point.column :]

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        hotkey = hk(key, modifiers)

        func = self.hotkeys.get(hotkey)
        if func is not None:
            cursor = self.textCursor()
            if func(cursor):
                self.setTextCursor(cursor)
                return

        accepted = False
        for behavior in self._keyPressBehaviors:
            acc = behavior.keyPressEvent(event, hotkey)
            if accepted and acc:
                print(f"WARNING: Multiple behaviors handle the same hotkey: {hotkey}")
            accepted |= acc

        if accepted:
            return

        super().keyPressEvent(event)

    def resizeEvent(self, e: QResizeEvent):
        """Handle resize events to update line number area geometry"""
        super().resizeEvent(e)
        for behavior in self._resizeBehaviors:
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
