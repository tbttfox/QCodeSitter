from __future__ import annotations
from typing import Callable, Optional, Collection, Type, TypeVar

from Qt import QtCore
from Qt.QtWidgets import QPlainTextEdit
from Qt.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPalette,
    QResizeEvent,
    QTextBlock,
)

from tree_sitter import Language

from .line_tracker import TrackedDocument
from .behaviors import Behavior, HasKeyPress, HasResize, HasHotkeys
from .tree_manager import TreeManager
from .syntax_analyzer import SyntaxAnalyzer
from .editor_options import EditorOptions
from .selection_manager import SelectionManager
from .multi_cursor_manager import MultiCursorManager
from .hotkey_manager import hk, HotkeyManager

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

        # Hotkeys
        self.hotkey_manager = HotkeyManager()
        self.hotkeys: dict[str, Callable[[], bool]] = {}

        self.tree_manager: TreeManager
        self.syntax_analyzer: SyntaxAnalyzer
        self.selection_manager: SelectionManager = SelectionManager(self)
        self.multi_cursor_manager: MultiCursorManager = MultiCursorManager(self)

        self._behaviors: list[Behavior] = []

        self.options.optionsUpdated.connect(self.updateOptions)
        self.updateOptions(list(self.options.keys()))
        self.update_hotkeys()

    def update_hotkeys(self):
        managers = [
            self.tree_manager,
            self.syntax_analyzer,
            self.selection_manager,
            self.multi_cursor_manager,
        ]
        groups = []
        for item in managers + self._behaviors:
            if item and isinstance(item, HasHotkeys):
                groups.append(item.getHotkeys())
        self.hotkey_manager.hotkey_groups = groups
        self.hotkeys = self.hotkey_manager.build_hotkey_dict()

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
        self.tree_manager = TreeManager(self, lang)
        self.syntax_analyzer = SyntaxAnalyzer(self.tree_manager, self._doc)
        self._doc.byteContentsChange.connect(self.tree_manager.update)
        self._doc.fullUpdateRequest.connect(self.tree_manager.fullUpdate)

    def addBehavior(
        self, behaviorCls: Type[T_Behavior]
    ) -> tuple[Optional[T_Behavior], T_Behavior]:
        """Set the given behavior to the class. If a behavior of the given type already exists, remove it
        Return both the old and newly instantiated behaviors.
        """
        old_bh = self.removeBehavior(behaviorCls)
        behavior = behaviorCls(self)
        self._behaviors.append(behavior)
        self.update_hotkeys()
        return old_bh, behavior

    def removeBehavior(self, behaviorCls: Type[T_Behavior]) -> Optional[T_Behavior]:
        """Remove all existing behaviors of the given type"""
        ridxs = []
        torem = []
        for i, bh in enumerate(self._behaviors):
            if type(bh) is behaviorCls:
                ridxs.append(i)
                torem.append(bh)
        for i in reversed(ridxs):
            self._behaviors.pop(i)
        for rem in torem:
            rem.remove()
        if not torem:
            return None
        if len(torem) > 1:
            print("Warning: Multiple behaviors of the same type found to remove")
        self.update_hotkeys()
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

    def keyPressEvent(self, e: QKeyEvent):
        # Check if multi-cursor manager wants to handle this
        if self.multi_cursor_manager.is_active():
            if self.multi_cursor_manager.handle_key_event(e):
                return

        key = e.key()
        modifiers = e.modifiers()
        hotkey = hk(key, modifiers)

        accepted = False
        for behavior in self._behaviors:
            if not isinstance(behavior, HasKeyPress):
                continue
            accepted = behavior.keyPressEvent(e, hotkey)
            if accepted:
                return

        func = self.hotkeys.get(hotkey)
        if func is not None:
            if func():
                return

        super().keyPressEvent(e)

    def mousePressEvent(self, e: QMouseEvent):
        """Handle mouse press events"""
        if e.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
            # Get the position at the click location
            cursor = self.cursorForPosition(e.pos())
            position = cursor.position()
            self.multi_cursor_manager.add_cursor_at_position(position)
            e.accept()
            return

        # Exit multi-cursor mode on normal click
        if self.multi_cursor_manager.is_active():
            self.multi_cursor_manager.exit_multi_cursor_mode()
        super().mousePressEvent(e)

    def resizeEvent(self, e: QResizeEvent):
        """Handle resize events to update line number area geometry"""
        super().resizeEvent(e)

        for behavior in self._behaviors:
            if isinstance(behavior, HasResize):
                behavior.resizeEvent(e)
