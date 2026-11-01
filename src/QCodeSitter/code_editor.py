from __future__ import annotations

import warnings
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from typing import TypeVar

from Qt import QtCore, QtGui, QtWidgets

from .behaviors import Behavior
from .clipboard import encode_multi_copy, split_multi_copy, tabs_to_spaces
from .constants import MIME
from .cursors.iterator import CursorIterator
from .cursors.multi import MultiCursor
from .cursors.state import CursorState
from .cursors.tracked import TrackedCursor
from .editor_options import EditorOptions
from .gui_colors import GuiColors, gui_color
from .gutters import GutterLayout
from .tracked_document import TrackedDocument
from .tree_manager import TreeManager
from .utils import KEY, MO, MOD, make_shortcut_action

T_Behavior = TypeVar("T_Behavior", bound=Behavior)

# Delete key -> (move operation, move operation with Ctrl held)
_DELETE_OPS: dict[KEY, tuple[MO, MO]] = {
    KEY.Key_Backspace: (MO.PreviousCharacter, MO.PreviousWord),
    KEY.Key_Delete: (MO.NextCharacter, MO.NextWord),
}


def _event_pos(event: QtGui.QMouseEvent | QtGui.QDropEvent) -> QtCore.QPoint:
    """The event position as a QPoint in both Qt5 and Qt6"""
    position = getattr(event, "position", None)
    return position().toPoint() if position is not None else event.pos()


class CodeEditor(QtWidgets.QPlainTextEdit):
    """A multi-cursor plain text editor that keeps a tree-sitter parse tree

    Features beyond plain editing are Behaviors added with `add_behavior`
    """

    # Emitted with (QPaintEvent, QPainter) to let behaviors paint over the viewport
    behaviorPaint = QtCore.Signal(object, object)
    aboutToUndoRedo = QtCore.Signal()
    # Emitted after an undo or redo, once the tree has been reparsed
    undoRedoFinished = QtCore.Signal()

    def __init__(
        self, options: EditorOptions, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent=parent)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._doc = TrackedDocument()
        self.setDocument(self._doc)
        self._selections: dict[str, list[QtWidgets.QTextEdit.ExtraSelection]] = {}
        self._behaviors: list[Behavior] = []
        self._keypress_behaviors: list[Behavior] = []
        self.options = options
        self.cursors = MultiCursor(self)
        self.citer = CursorIterator(self)
        self.gutters = GutterLayout(self)

        self._loaded = False
        self._can_join = False

        self.tree_manager = TreeManager(self)
        self._doc.byteContentsChange.connect(self.tree_manager.apply_edit)

        # The indent and clipboard options are read from self.options when used
        self._option_handlers = {
            "font": self._set_font,
            "language": self.tree_manager.set_language,
            "colors": self._set_colors,
            "tab_indent_width": lambda _width: self._update_tab_stop(),
        }
        self.options.optionsUpdated.connect(self._on_options_updated)

        # (modifier, action) pairs for the keys that run editor commands
        self._command_keys: dict[KEY, tuple[tuple[MOD, Callable[[], None]], ...]] = {
            KEY.Key_C: ((MOD.ControlModifier, self.copy),),
            KEY.Key_Insert: (
                (MOD.ControlModifier, self.copy),
                (MOD.ShiftModifier, self.paste),
            ),
            KEY.Key_V: ((MOD.ControlModifier, self.paste),),
            KEY.Key_X: ((MOD.ControlModifier, self.cut),),
            KEY.Key_Z: ((MOD.ControlModifier, self.undo),),
            KEY.Key_Y: ((MOD.ControlModifier, self.redo),),
        }
        for shortcut, slot in (
            ("Ctrl+D", self.cursors.add_next_occurrence),
            ("Ctrl+Alt+Up", self.cursors.add_above),
            ("Ctrl+Alt+Down", self.cursors.add_below),
            ("Ctrl+Shift+L", self.cursors.add_to_line_ends),
        ):
            self.addAction(make_shortcut_action(self, shortcut, slot))

    @property
    def is_loaded(self) -> bool:
        """Whether the editor has been shown, and has applied its options"""
        return self._loaded

    def textCursor(self) -> TrackedCursor:
        return TrackedCursor(self._doc, super().textCursor())

    def document(self) -> TrackedDocument:
        doc = super().document()
        if not isinstance(doc, TrackedDocument):
            raise TypeError("CodeEditor only works with a TrackedDocument")
        return doc

    @contextmanager
    def edit_session(self) -> Iterator[None]:
        """Group the edits made by one user action

        The cursors are snapshot once for all the citer passes, and the tree
        is only reparsed once at the end. Nested sessions join the outer one
        """
        if self.citer.active:
            yield
            return
        self.tree_manager.pause()
        try:
            with self.citer.session():
                yield
        finally:
            self.tree_manager.unpause()

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    def _on_options_updated(self, keylist: Collection[str]) -> None:
        # Everything gets applied when the editor is first shown
        if self._loaded:
            self.options.apply(self._option_handlers, keylist)

    def _set_font(self, font: QtGui.QFont) -> None:
        self.setFont(font)
        self._update_tab_stop()

    def _update_tab_stop(self) -> None:
        metrics = QtGui.QFontMetrics(self.font())
        width = self.options["tab_indent_width"]
        self.setTabStopDistance(width * metrics.horizontalAdvance(" "))

    def _set_colors(self, colors: GuiColors) -> None:
        palette = self.palette()
        role = QtGui.QPalette.ColorRole
        for roles, name in (
            ((role.Base, role.Window), "bg"),
            ((role.Text,), "fg"),
            ((role.Highlight,), "selection"),
        ):
            for color_role in roles:
                palette.setColor(color_role, gui_color(colors, name))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.options.apply(self._option_handlers, list(self.options.keys()))
            for bh in self._behaviors:
                bh.apply_all_options()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.gutters.place()

    # ------------------------------------------------------------------
    # Extra selections
    # ------------------------------------------------------------------

    def set_selections(
        self, source: str, selections: list[QtWidgets.QTextEdit.ExtraSelection]
    ) -> None:
        """Set the extra selections from one source, like a behavior

        Every source's selections are shown together, ordered by source name
        """
        self._selections[source] = selections
        self._update_editor_selections()

    def clear_selections(self, source: str) -> None:
        if source in self._selections:
            del self._selections[source]
            self._update_editor_selections()

    def selections(self, source: str) -> list[QtWidgets.QTextEdit.ExtraSelection]:
        """Get the extra selections set by a source"""
        return self._selections.get(source, [])

    def _update_editor_selections(self) -> None:
        merged = []
        for source in sorted(self._selections):
            merged.extend(self._selections[source])
        self.setExtraSelections(merged)

    # ------------------------------------------------------------------
    # Behaviors
    # ------------------------------------------------------------------

    def add_behavior(self, behavior_cls: type[T_Behavior]) -> T_Behavior:
        """Add a behavior, replacing any existing behavior of the same type"""
        self.remove_behavior(behavior_cls)
        behavior = behavior_cls(self)
        self._behaviors.append(behavior)
        if behavior.has_key_press():
            self._keypress_behaviors.append(behavior)
        behavior.shortcut_actions = behavior.get_hotkeys()
        self.addActions(behavior.shortcut_actions)
        return behavior

    def remove_behavior(self, behavior_cls: type[T_Behavior]) -> T_Behavior | None:
        """Remove the behavior of the given type, and return it if there was one"""
        removed = [bh for bh in self._behaviors if type(bh) is behavior_cls]
        if not removed:
            return None
        if len(removed) > 1:
            warnings.warn(
                f"Found {len(removed)} {behavior_cls.__name__} behaviors to remove",
                stacklevel=2,
            )
        self._behaviors = [b for b in self._behaviors if b not in removed]
        self._keypress_behaviors = [
            b for b in self._keypress_behaviors if b not in removed
        ]
        for bh in removed:
            for action in bh.shortcut_actions:
                self.removeAction(action)
                action.deleteLater()
            bh.remove()
        return removed[0]

    def get_behavior(self, behavior_cls: type[T_Behavior]) -> T_Behavior | None:
        for bh in self._behaviors:
            if type(bh) is behavior_cls:
                return bh
        return None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.modifiers() & MOD.AltModifier:
            self.cursors.add_at(self.cursorForPosition(_event_pos(event)).position())
            event.accept()
            return
        self.cursors.clear_secondary()
        super().mousePressEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self.viewport())
        try:
            self.behaviorPaint.emit(event, painter)
        finally:
            painter.end()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        with self.edit_session():
            for behavior in self._keypress_behaviors:
                if behavior.handle_key_press(event):
                    # The next typing starts a new undo step
                    self._can_join = False
                    return
            if not self._apply_editing_key(event):
                # Let Qt handle the keys we don't, like Ctrl+A
                super().keyPressEvent(event)

    def _apply_editing_key(self, event: QtGui.QKeyEvent) -> bool:
        """Apply the built-in editing keys to all the cursors

        Returns whether the key was handled
        """
        key = event.key()
        modifiers = event.modifiers()

        if key == KEY.Key_Escape:
            self.cursors.clear_secondary()
            return True

        typed = self._type_text(event)
        # Typing a word is a single undo step, so remember if this can join the next
        self._can_join = typed and (event.text().isalnum() or event.text() == "_")
        if typed:
            return True

        if modifiers == MOD.ControlModifier and key == KEY.Key_A:
            self.cursors.clear_secondary()
            return False

        delete_ops = _DELETE_OPS.get(key)
        if delete_ops is not None:
            self.delete(delete_ops[bool(modifiers & MOD.ControlModifier)])
            return True

        # Alt+arrow combinations are hotkeys, like Ctrl+Alt+Up to add a cursor
        if modifiers & MOD.AltModifier:
            return False

        select = bool(modifiers & MOD.ShiftModifier)
        word_mode = bool(modifiers & MOD.ControlModifier)
        return self.cursors.move(key, select, word_mode) or self._run_command_key(event)

    def _type_text(self, event: QtGui.QKeyEvent) -> bool:
        """Insert the text of a typing key at every cursor

        Returns whether the key typed text
        """
        text = event.text()
        if not text or not text.isprintable():
            return False
        if event.modifiers() not in (MOD.NoModifier, MOD.ShiftModifier):
            return False
        join = self._can_join and (text.isalnum() or text == "_")
        self.insert_text(text, join_edit=join)
        return True

    def _run_command_key(self, event: QtGui.QKeyEvent) -> bool:
        """Run the editor command for Tab, Enter, or a clipboard/undo shortcut"""
        key = event.key()
        if key == KEY.Key_Tab:
            if self.options["indent_using_tabs"]:
                self.insert_text("\t")
            else:
                self.insert_text(" " * self.options["space_indent_width"])
            return True
        # Key_Enter is the numpad
        if key == KEY.Key_Return:
            self.insert_text("\n")
            return True
        for modifier, command in self._command_keys.get(key, ()):
            if event.modifiers() & modifier:
                command()
                return True
        return False

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """Drop text through a TrackedCursor, so the tree sees the edit"""
        if not event.mimeData().hasText() and not event.mimeData().hasFormat(MIME):
            event.ignore()
            return

        main_cursor = self.textCursor()
        is_move = (
            event.source() == self
            and event.dropAction() == QtCore.Qt.DropAction.MoveAction
            and main_cursor.hasSelection()
        )
        target_pos = self.cursorForPosition(_event_pos(event)).position()

        sel_start = main_cursor.selectionStart()
        sel_end = main_cursor.selectionEnd()
        if is_move and sel_start <= target_pos <= sel_end:
            event.ignore()
            return

        with self.edit_session():
            if is_move:
                main_cursor.removeSelectedText()
                if target_pos > sel_start:
                    target_pos -= sel_end - sel_start

            # The drop location becomes the only cursor
            self.cursors.replace_all([CursorState(target_pos, target_pos)])
            self.insertFromMimeData(event.mimeData())
            event.accept()

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def setPlainText(self, text: str) -> None:
        self.cursors.clear_secondary()
        super().setPlainText(text)
        # This doesn't go through a TrackedCursor, so the tree has to be rebuilt
        self.tree_manager.full_update()

    def clear(self) -> None:
        self.setPlainText("")

    def undo(self) -> None:
        self._undo_redo(super().undo)

    def redo(self) -> None:
        self._undo_redo(super().redo)

    def _undo_redo(self, action: Callable[[], None]) -> None:
        # Qt's undo stack doesn't know about the secondary cursors, and its edits
        # don't go through a TrackedCursor. So drop the secondary cursors first,
        # and rebuild the tree once Qt has finished applying the change
        self.cursors.clear_secondary()
        self.aboutToUndoRedo.emit()
        action()
        QtCore.QTimer.singleShot(0, self._after_undo_redo)

    def _after_undo_redo(self) -> None:
        self.tree_manager.full_update()
        self.undoRedoFinished.emit()

    # The public editing methods each make one undo step and one reparse

    def insert_text(self, text: str, join_edit: bool = False) -> None:
        """Type text at every cursor, replacing their selections"""
        with self.edit_session():
            for cursor in self.citer.iterate_cursors(join_edit=join_edit):
                cursor.insertText(text)
                self.citer.cursor_completed()

    def delete(self, movement: MO) -> None:
        """Delete each cursor's selection, or the text it would move over

        Args:
            movement: Like MO.PreviousCharacter for Backspace, or MO.NextWord
                for Ctrl+Delete
        """
        with self.edit_session():
            for cursor in self.citer.iterate_cursors():
                if not cursor.hasSelection():
                    cursor.movePosition(movement, QtGui.QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                self.citer.cursor_completed()

    def copy(self) -> None:
        """Copy the text of every cursor to the clipboard, see clipboard.py"""
        texts = self.cursors.selected_texts()
        if self.options["copy_indents_as_spaces"]:
            width = self.options["space_indent_width"]
            texts = [tabs_to_spaces(t, width) for t in texts]
        QtWidgets.QApplication.clipboard().setMimeData(encode_multi_copy(texts))

    def cut(self) -> None:
        self.copy()
        with self.edit_session():
            for cursor in self.citer.iterate_cursors():
                if cursor.hasSelection():
                    cursor.removeSelectedText()
                self.citer.cursor_completed()

    def paste(self) -> None:
        self.insertFromMimeData(QtWidgets.QApplication.clipboard().mimeData())

    def insertFromMimeData(self, source: QtCore.QMimeData) -> None:
        """Insert mime data at every cursor, through TrackedCursors"""
        text = source.text()
        if not text:
            return
        parts = split_multi_copy(source, len(self.cursors.secondary) + 1)
        if parts is None:
            self.insert_text(text)
            return
        with self.edit_session():
            # There is a part for every cursor, so this never runs out
            for i, cursor in enumerate(self.citer.iterate_cursors()):
                cursor.insertText(parts[i])
                self.citer.cursor_completed()
