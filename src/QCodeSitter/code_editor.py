from __future__ import annotations

import warnings
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from typing import TypeVar

from Qt import QtCore, QtGui, QtWidgets
from tree_sitter import Language

from .behaviors import Behavior
from .cursors.clipboard import encode_multi_copy, split_multi_copy, tabs_to_spaces
from .cursors.iterator import CursorIterator
from .cursors.line_edits import edit_joined_spans
from .cursors.multi import MultiCursor
from .cursors.state import CursorState
from .cursors.tracked import TrackedCursor
from .editing_keys import EditingKeys
from .editor_options import EditorOptions, check_option_keys
from .gui_colors import GuiColors, gui_color
from .gutters import GutterLayout
from .tracked_document import TrackedDocument
from .tree_manager import TreeManager
from .utils import MM, MO, MOD, event_pos, make_shortcut_action

T_Behavior = TypeVar("T_Behavior", bound=Behavior)


class CodeEditor(QtWidgets.QPlainTextEdit):
    """A multi-cursor plain text editor that keeps a tree-sitter parse tree

    Features beyond plain editing are Behaviors added with `add_behavior`.
    add_behavior, remove_behavior and get_behavior all match a type and its
    subclasses
    """

    # Emitted with (QPaintEvent, QPainter) to let behaviors paint over the viewport
    behaviorPaint = QtCore.Signal(object, object)
    # Emitted after an undo or redo, once the tree has been reparsed. Behaviors
    # that follow the tree can use TreeManager.reparsed instead
    undoRedoFinished = QtCore.Signal()

    def __init__(
        self, options: EditorOptions, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent=parent)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._doc = TrackedDocument()
        super().setDocument(self._doc)
        self._selections: dict[str, list[QtWidgets.QTextEdit.ExtraSelection]] = {}
        self._behaviors: list[Behavior] = []
        self._keypress_behaviors: list[Behavior] = []
        self.options = options
        self.cursors = MultiCursor(self)
        self.citer = CursorIterator(self)
        self.gutters = GutterLayout(self)

        self._loaded = False

        self.tree_manager = TreeManager(self._doc)
        self._doc.byteContentsChange.connect(self.tree_manager.apply_edit)

        # The indent and clipboard options are read from self.options when used
        self._option_handlers = {
            "font": self._set_font,
            "language": self._set_language,
            "colors": self._set_colors,
            "tab_indent_width": lambda _width: self._update_tab_stop(),
        }
        check_option_keys(self._option_handlers)
        self.options.apply(self._option_handlers, self._option_handlers)
        self.options.optionsUpdated.connect(self._on_options_updated)

        self.keys = EditingKeys(self)
        for shortcut, slot in (
            ("Ctrl+D", self.cursors.add_next_occurrence),
            ("Ctrl+Alt+Up", self.cursors.add_above),
            ("Ctrl+Alt+Down", self.cursors.add_below),
            ("Ctrl+Shift+L", self.cursors.add_to_line_ends),
        ):
            self.addAction(make_shortcut_action(self, shortcut, slot))

    def textCursor(self) -> TrackedCursor:
        return TrackedCursor(self._doc, super().textCursor())

    def document(self) -> TrackedDocument:
        return self._doc

    def setDocument(self, document: QtGui.QTextDocument) -> None:
        """Not supported. The tree, cursors and behaviors are bound to the editor's
        own TrackedDocument
        """
        raise NotImplementedError("CodeEditor can't change its TrackedDocument")

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

    def load(self) -> None:
        """Set the language, which parses and highlights the document

        Those are the expensive part of making an editor, so they wait until
        the editor is first shown. Call this to load an editor that isn't shown
        """
        if not self._loaded:
            self._loaded = True
            self.options.apply(self._option_handlers, ["language"])

    def _on_options_updated(self, keylist: Collection[str]) -> None:
        self.options.apply(self._option_handlers, keylist)

    def _set_language(self, language: Language) -> None:
        if self._loaded:
            self.tree_manager.set_language(language)

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
        self.load()

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
        self._selections[source] = list(selections)
        self._update_editor_selections()

    def clear_selections(self, source: str) -> None:
        if source in self._selections:
            del self._selections[source]
            self._update_editor_selections()

    def selections(self, source: str) -> list[QtWidgets.QTextEdit.ExtraSelection]:
        """Get a copy of the extra selections set by a source"""
        return list(self._selections.get(source, []))

    def _update_editor_selections(self) -> None:
        merged = []
        for source in sorted(self._selections):
            merged.extend(self._selections[source])
        self.setExtraSelections(merged)

    # ------------------------------------------------------------------
    # Behaviors
    # ------------------------------------------------------------------

    def add_behavior(self, behavior_cls: type[T_Behavior]) -> T_Behavior:
        """Add a behavior, replacing any installed behavior of that type or of a
        subclass of it

        Adding a subclass doesn't replace its base class; call
        remove_behavior(Base) first to swap one in
        """
        self.remove_behavior(behavior_cls)
        behavior = behavior_cls(self)
        self._behaviors.append(behavior)
        if behavior.handles_key_presses():
            self._keypress_behaviors.append(behavior)
            # The sort is stable, so the same priorities keep the order they were added
            self._keypress_behaviors.sort(key=lambda bh: -bh.KEY_PRIORITY)
        behavior.shortcut_actions = behavior.get_hotkeys()
        self.addActions(behavior.shortcut_actions)
        return behavior

    def remove_behavior(self, behavior_cls: type[T_Behavior]) -> T_Behavior | None:
        """Remove the behaviors of a type or of its subclasses, and return the
        first one if there was one
        """
        removed = [bh for bh in self._behaviors if isinstance(bh, behavior_cls)]
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
        """Get the behavior of a type, or of a subclass of it"""
        for bh in self._behaviors:
            if isinstance(bh, behavior_cls):
                return bh
        return None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.modifiers() & MOD.AltModifier:
            self.cursors.add_at(self.cursorForPosition(event_pos(event)).position())
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
                    self.keys.end_undo_step()
                    return
            if not self.keys.handle_key_press(event):
                # Let Qt handle the keys we don't, like Ctrl+A
                with self._qt_edits():
                    super().keyPressEvent(event)

    def inputMethodEvent(self, event: QtGui.QInputMethodEvent) -> None:
        with self._qt_edits():
            super().inputMethodEvent(event)

    @contextmanager
    def _qt_edits(self) -> Iterator[None]:
        """Rebuild the tree if Qt edits the document itself

        Qt's own edits don't go through a TrackedCursor, so tree-sitter isn't told
        about them, and they don't update the secondary cursors, which are dropped.
        Every edit changes the revision, even with undo off. The resync also
        runs if the block raises, so an edit made before the error isn't lost
        """
        revision = self._doc.revision()
        try:
            yield
        finally:
            if self._doc.revision() != revision:
                self.cursors.clear_secondary()
                self.tree_manager.parse_from_scratch()

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        self.create_context_menu().exec_(event.globalPos())

    def create_context_menu(self) -> QtWidgets.QMenu:
        """Make the right click menu

        Its actions call this editor's methods. Qt's standard menu calls the
        C++ slots instead, which only edit the primary cursor, and don't
        update the tree
        """
        menu = QtWidgets.QMenu(self)
        doc = self.document()
        selected = self.textCursor().hasSelection()
        sections = (
            (
                ("&Undo", self.undo, doc.isUndoAvailable()),
                ("&Redo", self.redo, doc.isRedoAvailable()),
            ),
            (
                ("Cu&t", self.cut, selected),
                ("&Copy", self.copy, selected),
                ("&Paste", self.paste, self.canPaste()),
                ("Delete", lambda: self.delete(MO.NextCharacter), selected),
            ),
            (("Select All", self.selectAll, not doc.isEmpty()),),
        )
        for i, section in enumerate(sections):
            if i:
                menu.addSeparator()
            for text, slot, enabled in section:
                action = menu.addAction(text)
                action.setEnabled(enabled)
                action.triggered.connect(slot)
        return menu

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """Drop text through a TrackedCursor, so the tree sees the edit"""
        # insertFromMimeData only inserts text, which multi-copy data also has
        if not event.mimeData().text():
            event.ignore()
            return

        main_cursor = self.textCursor()
        is_move = (
            event.source() == self
            and event.dropAction() == QtCore.Qt.DropAction.MoveAction
            and main_cursor.hasSelection()
        )
        target_pos = self.cursorForPosition(event_pos(event)).position()

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
        with self._qt_edits():
            super().setPlainText(text)

    def insertPlainText(self, text: str) -> None:
        """Type text at every cursor, like `insert_text`"""
        self.insert_text(text)

    def appendPlainText(self, text: str) -> None:
        """Add a line of text to the end of the document"""
        with self._qt_edits():
            super().appendPlainText(text)

    def appendHtml(self, html: str) -> None:
        """Add a paragraph of html to the end of the document"""
        with self._qt_edits():
            super().appendHtml(html)

    def clear(self) -> None:
        self.setPlainText("")

    def undo(self) -> None:
        self._undo_redo(super().undo)

    def redo(self) -> None:
        self._undo_redo(super().redo)

    def _undo_redo(self, action: Callable[[], None]) -> None:
        # Qt's undo stack doesn't know about the secondary cursors
        with self._qt_edits():
            action()
        self.undoRedoFinished.emit()

    # The public editing methods each make one undo step and one reparse

    def insert_text(self, text: str, join_edit: bool = False) -> None:
        """Type text at every cursor, replacing their selections"""
        with self.edit_session():
            for cursor in self.citer.iterate_cursors(
                join_edit=join_edit, complete_all=True
            ):
                cursor.insertText(text)

    def delete(self, movement: MO) -> None:
        """Delete each cursor's selection, or the text it would move over

        Spans that overlap are deleted together, so a cursor whose span another
        cursor deleted doesn't go on to delete more

        Args:
            movement: Like MO.PreviousCharacter for Backspace, or MO.NextWord
                for Ctrl+Delete
        """

        def span(cursor: QtGui.QTextCursor) -> tuple[int, int]:
            if not cursor.hasSelection():
                cursor.movePosition(movement, MM.KeepAnchor)
            return cursor.selectionStart(), cursor.selectionEnd()

        def delete_join(
            cursor: QtGui.QTextCursor, joined: tuple[int, int], shift: int
        ) -> None:
            cursor.setPosition(joined[0] + shift)
            cursor.setPosition(joined[1] + shift, MM.KeepAnchor)
            cursor.removeSelectedText()

        with self.edit_session():
            edit_joined_spans(self.citer, span, delete_join)

    def copy(self) -> None:
        """Copy the text of every cursor to the clipboard, see cursors/clipboard.py"""
        texts = self.cursors.selected_texts()
        # Like Qt, copying nothing leaves the clipboard alone
        if not any(texts):
            return
        if self.options["copy_indents_as_spaces"]:
            width = self.options["space_indent_width"]
            texts = [tabs_to_spaces(t, width) for t in texts]
        QtWidgets.QApplication.clipboard().setMimeData(encode_multi_copy(texts))

    def cut(self) -> None:
        self.copy()
        with self.edit_session():
            for cursor in self.citer.iterate_cursors(complete_all=True):
                if cursor.hasSelection():
                    cursor.removeSelectedText()

    def paste(self) -> None:
        # An empty clipboard has no mime data on some platforms
        source = QtWidgets.QApplication.clipboard().mimeData()
        if source is not None:
            self.insertFromMimeData(source)

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
            for i, cursor in enumerate(self.citer.iterate_cursors(complete_all=True)):
                cursor.insertText(parts[i])
