from __future__ import annotations
from typing import Union, Optional, Collection, Type, TypeVar

from dataclasses import dataclass
from Qt import QtGui
from Qt import QtCore
from Qt import QtWidgets

from tree_sitter import Language

from .constants import MIME
from .utils import len16
from .behaviors import Behavior, HasKeyPress, HasResize, HasHotkeys, HasPaint
from .line_tracker import TrackedDocument
from .tree_manager import TreeManager
from .syntax_analyzer import SyntaxAnalyzer
from .editor_options import EditorOptions

from QtShortcutManager import ShortcutManager, ShortcutSlot, ShortcutSlotGroup


T_Behavior = TypeVar("T_Behavior", bound=Behavior)


@dataclass
class CursorState:
    """Represents a single cursor's position and selection"""

    anchor: int  # UTF-16 position
    position: int  # UTF-16 position

    @classmethod
    def fromQt(cls, cursor: QtGui.QTextCursor) -> CursorState:
        return cls(cursor.anchor(), cursor.position())

    def setPosition(self, val: int, moveMode=QtGui.QTextCursor.MoveMode.MoveAnchor):
        if moveMode == QtGui.QTextCursor.MoveMode.MoveAnchor:
            self.anchor = val
        self.position = val

    def hasSelection(self) -> bool:
        """Returns True if this cursor has a selection"""
        return self.anchor != self.position

    def selectionStart(self) -> int:
        """Returns the start position of the selection (or cursor position if no selection)"""
        return min(self.anchor, self.position)

    def selectionEnd(self) -> int:
        """Returns the end position of the selection (or cursor position if no selection)"""
        return max(self.anchor, self.position)

    def apply(self, cursor: QtGui.QTextCursor) -> QtGui.QTextCursor:
        """Apply this state to a QtGui.QTextCursor"""
        cursor.setPosition(self.anchor)
        cursor.setPosition(self.position, QtGui.QTextCursor.MoveMode.KeepAnchor)
        return cursor

    def update(self, cursor: QtGui.QTextCursor):
        self.anchor = cursor.anchor()
        self.position = cursor.position()

    def offset(self, offset: int):
        """Offset this state by a given number of characters"""
        self.anchor += offset
        self.position += offset

    def build_cursor(self, document: QtGui.QTextDocument) -> QtGui.QTextCursor:
        """Build a cursor for a given document"""
        cursor = QtGui.QTextCursor(document)
        cursor.setPosition(self.anchor)
        cursor.setPosition(self.position, QtGui.QTextCursor.MoveMode.KeepAnchor)
        return cursor

    def __eq__(self, other) -> bool:
        if not isinstance(other, CursorState):
            return False
        return self.anchor == other.anchor and self.position == other.position

    def __hash__(self) -> int:
        return hash((self.anchor, self.position))


class CursorIterator:
    """A class to manage the key press event for multiple cursors
    Each cursor can be completed separately from the others.

    You can iterate over an instance of this class multiple times,
    and it will keep track of all the cursors, and updating the
    position of cursors as previous cursors in the list edit text
    """

    def __init__(self, editor: CodeEditor):
        self.editor = editor
        self._multicursor_offset = 0
        self._cursor_completed = False
        self._cursor_cmp_list: list[bool] = []
        self._cursor_srt_list: list[CursorState] = []
        self._cursor_primary_idx: int = 0
        self.handled = False

        cursors, primary_index = self.editor.get_all_cursors()
        self._cursor_srt_list = cursors
        self._cursor_cmp_list = [False] * len(cursors)
        self._cursor_primary_idx = primary_index

    def update_offset(self, val):
        """Keep track of the position delta for the current cursor
        Only useful inside an iterate_cursors loop
        """
        self._multicursor_offset += val

    def cursor_completed(self):
        """Mark the current cursor as completed
        Only useful inside an iterate_cursors loop
        """
        self._cursor_completed = True

    def iterate_cursors(
        self, join_edit: bool = False, no_position_update: bool = False
    ):
        """Iterate over all non-completed cursor states for editing in a single edit block"""
        # TODO: Figure out how to combine single insertions

        qt_cursor = self.editor.textCursor()
        if join_edit:
            qt_cursor.joinPreviousEditBlock()
        else:
            qt_cursor.beginEditBlock()

        self._multicursor_offset = 0
        self.handled = False
        for i, state in enumerate(self._cursor_srt_list):
            # Always offset the cursors because a previous
            # one may have edited the text
            state.offset(self._multicursor_offset)
            if self._cursor_cmp_list[i]:
                # cursor is already completed
                continue

            state.apply(qt_cursor)
            self._cursor_completed = False
            is_primary = i == self._cursor_primary_idx
            yield qt_cursor, is_primary
            if not no_position_update:
                state.update(qt_cursor)
            self._cursor_cmp_list[i] = self._cursor_completed
            self.handled = True

        qt_cursor.endEditBlock()
        if self.handled:
            all_cursors = self._cursor_srt_list[:]
            primary_cursor = all_cursors.pop(self._cursor_primary_idx)
            all_cursors.insert(0, primary_cursor)
            self.editor._set_all_cursors(all_cursors)


class CodeEditor(QtWidgets.QPlainTextEdit):
    gutterResize = QtCore.Signal()

    def __init__(
        self,
        options: EditorOptions,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self._doc: TrackedDocument = TrackedDocument()
        self._clipboard_cursor_counts: list[int] = []
        self._selections: dict[str, list[QtWidgets.QTextEdit.ExtraSelection]] = {}
        self._behaviors: list[Behavior] = []
        self._updatingMargins = False
        self.citer: CursorIterator

        self.gutterWidths: dict[str, int] = {}
        self.gutterOrder: list[str] = []

        self.setDocument(self._doc)
        self.options = options
        self.secondary_cursors: list[CursorState] = []

        self.shortcut_manager = ShortcutManager()

        self.tree_manager: TreeManager
        self.syntax_analyzer: SyntaxAnalyzer

        # TODO: Get this data from options
        self.space_indent_width: int = 4
        self.indent_using_tabs: bool = False

        # Visual appearance
        self.primary_cursor_color = QtGui.QColor(255, 255, 255, 255)
        self.secondary_cursor_color = QtGui.QColor(180, 180, 180, 200)

        self.updateOptions(list(self.options.keys()))

    def updateGutter(self):
        current_margins = self.viewportMargins()
        current_margins.setLeft(sum(self.gutterWidths.values()))
        self.setViewportMargins(current_margins)

    def resizeEvent(self, e: QtGui.QResizeEvent):
        """Handle resize events to update line number area geometry"""
        super().resizeEvent(e)

        for behavior in self._behaviors:
            if isinstance(behavior, HasResize):
                behavior.resizeEvent(e)

        self.gutterResize.emit()

    def set_selections(
        self, source: str, selections: list[QtWidgets.QTextEdit.ExtraSelection]
    ):
        """Set selections for a specific source (behavior)

        Args:
            source: Identifier for the source behavior (e.g., "bracket_matching", "selection_highlight")
            selections: List of extra selections to apply
        """
        self._selections[source] = selections
        self._update_editor_selections()

    def clear_selections(self, source: str):
        """Clear selections for a specific source

        Args:
            source: Identifier for the source behavior
        """
        if source in self._selections:
            del self._selections[source]
            self._update_editor_selections()

    def _update_editor_selections(self):
        """Merge all selections and update the editor"""
        merged = []
        for source in sorted(self._selections.keys()):
            merged.extend(self._selections[source])

        self.setExtraSelections(merged)

    def update_shortcuts(self):
        """Update the shortcut manager with all user-configurable shortcuts.

        This collects shortcuts from managers and behaviors that implement HasHotkeys
        and loads them into the ShortcutManager. These are user-configurable shortcuts
        with modifier keys (Ctrl, Alt, Shift), not intrinsic editing behaviors.
        """
        # Unload old shortcuts first to avoid duplicates
        for group in self.shortcut_manager.shortcut_groups:
            for slot in group.slots:
                if slot.action is not None:
                    # Remove action from widget before unloading
                    self.removeAction(slot.action)
                slot.unload()

        groups = []
        groups.append(self.getHotkeys())
        for item in self._behaviors:
            if item and isinstance(item, HasHotkeys):
                groups.append(item.getHotkeys())

        self.shortcut_manager.shortcut_groups = groups

        # Load shortcuts and connect them to actions
        # This creates QAction objects for each shortcut and connects them to their target functions
        for group in groups:
            for slot in group.slots:
                # Convert assigned QtGui.QKeySequence objects to strings for loading
                assigned_strings = [seq.toString() for seq in slot.assigned]
                slot.load(assigned_strings, parent=self)

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
        palette.setColor(
            QtGui.QPalette.ColorRole.Base, QtGui.QColor(colors["bg"])
        )  # Background
        palette.setColor(
            QtGui.QPalette.Window, QtGui.QColor(colors["bg"])
        )  # Window background
        palette.setColor(
            QtGui.QPalette.Text, QtGui.QColor(colors["fg"])
        )  # Window background
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def setLanguage(self, lang: Language):
        self.tree_manager = TreeManager(self, lang)
        self.syntax_analyzer = SyntaxAnalyzer(self.tree_manager, self._doc)
        self._doc.byteContentsChange.connect(self.tree_manager.update)
        self._doc.fullUpdateRequest.connect(self.tree_manager.fullUpdate)
        self.tree_manager.fullUpdate()

    def addBehavior(
        self, behaviorCls: Type[T_Behavior]
    ) -> tuple[Optional[T_Behavior], T_Behavior]:
        """Set the given behavior to the class. If a behavior of the given type already exists, remove it
        Return both the old and newly instantiated behaviors.
        """
        old_bh = self.removeBehavior(behaviorCls)
        behavior = behaviorCls(self)
        self._behaviors.append(behavior)
        self.update_shortcuts()
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
        self.update_shortcuts()
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

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        """Handle mouse press events"""
        if e.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
            # Alt+Click to add cursor at position
            cursor = self.cursorForPosition(e.pos())
            position = cursor.position()
            self.add_cursor_at_position(position)
            e.accept()
            return

        # Exit multi-cursor mode on normal click
        self.exit_multi_cursor_mode()
        super().mousePressEvent(e)

    def paintEvent(self, e: QtGui.QPaintEvent):
        """Handle paint events to allow behaviors to customize rendering"""
        super().paintEvent(e)

        # Create a painter on the viewport for behaviors to use
        painter = QtGui.QPainter(self.viewport())
        try:
            for behavior in self._behaviors:
                if isinstance(behavior, HasPaint):
                    behavior.paintEvent(e, painter)
        finally:
            painter.end()

    def getHotkeys(self) -> ShortcutSlotGroup:
        """Return user-configurable shortcuts for multi-cursor operations"""
        slots = []

        slots.append(
            ShortcutSlot(
                name="Add Next Occurrence",
                targetFunc=self.add_next_occurrence,
                defaults=[QtGui.QKeySequence("Ctrl+D")],
            )
        )

        slots.append(
            ShortcutSlot(
                name="Add Cursor Above",
                targetFunc=self.add_cursor_above,
                defaults=[QtGui.QKeySequence("Ctrl+Alt+Up")],
            )
        )

        slots.append(
            ShortcutSlot(
                name="Add Cursor Below",
                targetFunc=self.add_cursor_below,
                defaults=[QtGui.QKeySequence("Ctrl+Alt+Down")],
            )
        )

        slots.append(
            ShortcutSlot(
                name="Add Cursors to Line Ends",
                targetFunc=self.add_cursors_to_line_ends,
                defaults=[QtGui.QKeySequence("Ctrl+Shift+L")],
            )
        )

        return ShortcutSlotGroup("Multi-Cursor", slots=slots)

    def get_primary_cursor(self) -> CursorState:
        """Convert Qt's primary cursor to QtGui.QTextCursor"""
        return CursorState.fromQt(self.textCursor())

    def set_primary_cursor(self, state: CursorState):
        """Update Qt's primary cursor from CursorState"""
        self.setTextCursor(state.apply(self.textCursor()))

    def get_all_cursors(self) -> tuple[list[CursorState], int]:
        """Return primary + all secondary cursors sorted by position
        And the index of the primary cursor"""
        primary = self.get_primary_cursor()
        all_cursors = [primary] + self.secondary_cursors
        ret = sorted(all_cursors, key=lambda c: c.selectionStart())
        return ret, ret.index(primary)

    def _set_all_cursors(self, cursors: list[CursorState]):
        """Update all cursor positions from a list of CursorStates

        The first cursor becomes the primary, the rest become secondaries.
        Merges overlapping cursors.
        """
        if not cursors:
            self.exit_multi_cursor_mode()
            return

        # Merge overlapping cursors
        merged = self._merge_overlapping_cursors(cursors)

        # First cursor is primary
        self.set_primary_cursor(merged[0])

        # Rest are secondary
        self.secondary_cursors = merged[1:]

        self._update_visual()

    def _merge_overlapping_cursors(
        self, cursors: list[CursorState]
    ) -> list[CursorState]:
        """Merge cursors that overlap or are adjacent"""
        if len(cursors) <= 1:
            return cursors

        # Sort by start position
        cursors = sorted(cursors, key=lambda c: c.selectionStart())

        merged = [cursors[0]]
        for cursor in cursors[1:]:
            last = merged[-1]

            # Check for overlap or adjacency
            if cursor.selectionStart() <= last.selectionEnd():
                # Merge: extend the last cursor
                new_anchor = min(last.anchor, cursor.anchor)
                new_position = max(last.position, cursor.position)
                merged[-1] = CursorState(new_anchor, new_position)
            else:
                merged.append(cursor)

        return merged

    def _update_visual(self):
        """Update visual rendering of secondary cursors"""
        if not self.secondary_cursors:
            self.clear_selections("multi_cursor")
            return

        self._render_cursors()

    def _render_cursors(self):
        """Render secondary cursors as ExtraSelections"""
        doc = self.document()
        max_pos = doc.characterCount()

        selections = []
        for state in self.secondary_cursors:
            # Validate state position is within document bounds
            if state.position < 0 or state.position > max_pos:
                continue  # Skip invalid state
            if state.anchor < 0 or state.anchor > max_pos:
                continue  # Skip invalid state

            # Create ExtraSelection
            selection = QtWidgets.QTextEdit.ExtraSelection()

            # Format for the cursor/selection
            fmt = QtGui.QTextCharFormat()

            if state.hasSelection():
                # Selection background
                fmt.setBackground(self.secondary_cursor_color.lighter(150))
                selection.cursor = state.build_cursor(doc)
            else:
                # For cursor positions (no selection), we need to select one character
                # to make it visible. If at end of line, select the newline.
                # If at end of document, select backwards one char.

                selstate = CursorState(state.anchor, state.position)
                if selstate.position < max_pos - 1:
                    # Select next character
                    selstate.setPosition(selstate.position)
                    selstate.setPosition(
                        selstate.position + 1, QtGui.QTextCursor.MoveMode.KeepAnchor
                    )
                elif selstate.position > 0 and selstate.position <= max_pos:
                    # At end - select previous character
                    selstate.setPosition(selstate.position - 1)
                    selstate.setPosition(
                        min(selstate.position, max_pos),
                        QtGui.QTextCursor.MoveMode.KeepAnchor,
                    )

                selection.cursor = selstate.build_cursor(doc)
                fmt.setBackground(self.secondary_cursor_color)
                fmt.setForeground(
                    QtGui.QColor(0, 0, 0)
                )  # Black text on gray background

            selection.format = fmt
            selections.append(selection)

        self.set_selections("multi_cursor", selections)

    def exit_multi_cursor_mode(self):
        """Exit multi-cursor mode, keep only primary cursor"""
        self.secondary_cursors.clear()
        self.clear_selections("multi_cursor")

    def undo(self):
        """Override undo to exit multi-cursor mode first"""
        # Qt's undo system doesn't track our CursorState positions, so we exit
        # multi-cursor mode to avoid cursor position desync after undo
        self.exit_multi_cursor_mode()
        super().undo()

    def redo(self):
        """Override redo to exit multi-cursor mode first"""
        # Qt's undo system doesn't track our CursorState positions, so we exit
        # multi-cursor mode to avoid cursor position desync after redo
        self.exit_multi_cursor_mode()
        super().redo()

    def add_next_occurrence(self):
        """Add cursor at next occurrence of current selection

        Returns True if a cursor was added, False otherwise
        """
        primary = self.get_primary_cursor()
        cursor = self.textCursor()

        # Get search text from primary cursor selection
        if not primary.hasSelection():
            # No selection - select word under cursor first
            cursor.select(QtGui.QTextCursor.SelectionType.WordUnderCursor)
            if not cursor.hasSelection():
                return
            self.setTextCursor(cursor)
            primary = self.get_primary_cursor()

        search_text = cursor.selectedText()
        if not search_text:
            return

        # Find next occurrence after the last cursor
        all_cursors, _primary_index = self.get_all_cursors()
        search_start = all_cursors[-1].selectionEnd()

        next_pos = self._find_next(search_text, search_start)
        if next_pos >= 0:
            # Add new secondary cursor at match
            new_cursor = CursorState(next_pos, next_pos + len(search_text))
            self.secondary_cursors.append(new_cursor)
            self._update_visual()
            return

        # Wrap around to beginning
        next_pos = self._find_next(search_text, 0)
        if next_pos >= 0 and next_pos < all_cursors[0].selectionStart():
            new_cursor = CursorState(next_pos, next_pos + len(search_text))
            self.secondary_cursors.append(new_cursor)
            self._update_visual()

    def _find_next(self, search_text: str, start_pos: int) -> int:
        """Find next occurrence of search_text starting from start_pos

        Returns position of match, or -1 if not found
        """
        cursor = QtGui.QTextCursor(self.document())
        cursor.setPosition(start_pos)

        # Use document's find method
        found = self.document().find(search_text, cursor)

        if not found.isNull():
            return found.selectionStart()
        return -1

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        self.citer = CursorIterator(self)
        for behavior in self._behaviors:
            if isinstance(behavior, HasKeyPress):
                if behavior.keyPressEvent(e):
                    return

        if self._handle_key_event(e):
            return

        # I think this is required to handle the rest of the hotkeys
        super().keyPressEvent(e)

    def _handle_key_event(self, event: QtGui.QKeyEvent) -> bool:
        """Handle key events for multi-cursor mode

        Returns True if the event was handled, False otherwise
        """
        KEY = QtCore.Qt.Key
        nomod = QtCore.Qt.KeyboardModifier.NoModifier
        shift = QtCore.Qt.KeyboardModifier.ShiftModifier
        ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
        alt = QtCore.Qt.KeyboardModifier.AltModifier

        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        # Exit on Escape
        if key == KEY.Key_Escape:
            self.exit_multi_cursor_mode()
            return True

        # Handle printable characters (normal typing)
        if text and text.isprintable() and modifiers in (nomod, shift):
            self.insert_text(text)
            return True

        # Handle special keys
        if key == KEY.Key_Backspace:
            if modifiers & ctrl:
                # FIXME: Bug in this when the cursor is at the end of the document
                self.delete_word_backward()
            else:
                self.backspace()
            return True

        if key == KEY.Key_Delete:
            if modifiers & ctrl:
                self.delete_word_forward()
            else:
                self.delete_char()
            return True

        # Handle arrow keys (but not Ctrl+Alt+Up/Down - those are for adding cursors)
        if modifiers & alt:
            # Let Alt+arrow combinations be handled by hotkeys
            return False

        select = bool(modifiers & shift)
        word_mode = bool(modifiers & ctrl)

        moved = self.move_cursors(key, select, word_mode)
        if moved:
            return True

        # Handle Tab
        if key == KEY.Key_Tab:
            if self.indent_using_tabs:
                self.insert_text("\t")
            else:
                self.insert_text(" " * self.space_indent_width)
            return True

        # Key_Enter is the numpad
        if key == KEY.Key_Return:
            self.insert_text("\n")
            return True

        if key == KEY.Key_C and modifiers & ctrl:
            self.copy()
            return True

        if key == KEY.Key_Insert and modifiers & ctrl:
            self.copy()
            return True

        if key == KEY.Key_V and modifiers & ctrl:
            self.paste()
            return True

        if key == KEY.Key_Insert and modifiers & shift:
            self.paste()
            return True

        if key == KEY.Key_X and modifiers & ctrl:
            self.cut()
            return True

        if key == KEY.Key_Z and modifiers & ctrl:
            self.undo()
            return True

        if key == KEY.Key_Y and modifiers & ctrl:
            self.redo()
            return True

        return False

    def insert_text(self, text: str, join_edit: bool = False):
        tlen = len16(text)
        for cursor, is_primary in self.citer.iterate_cursors(join_edit=join_edit):
            cursor.insertText(text)
            self.citer.update_offset(tlen)
            self.citer.cursor_completed()

    def _delete_movement(self, movement: QtGui.QTextCursor.MoveOperation):
        """Delete based on a move operation at cursor at all positions"""
        for cursor, is_primary in self.citer.iterate_cursors():
            if not cursor.hasSelection():
                cursor.movePosition(movement, QtGui.QTextCursor.MoveMode.KeepAnchor)
            self.citer.update_offset(cursor.selectionStart() - cursor.selectionEnd())
            cursor.removeSelectedText()

            self.citer.cursor_completed()

    def backspace(self):
        self._delete_movement(QtGui.QTextCursor.MoveOperation.PreviousCharacter)

    def delete_char(self):
        self._delete_movement(QtGui.QTextCursor.MoveOperation.NextCharacter)

    def delete_word_forward(self):
        self._delete_movement(QtGui.QTextCursor.MoveOperation.NextWord)

    def delete_word_backward(self):
        self._delete_movement(QtGui.QTextCursor.MoveOperation.PreviousWord)

    def _smart_home(
        self, qt_cursor: QtGui.QTextCursor, state: CursorState, select: bool
    ) -> CursorState:
        MOVE = QtGui.QTextCursor.MoveOperation
        MODE = QtGui.QTextCursor.MoveMode

        qt_cursor.movePosition(MOVE.StartOfBlock, MODE.MoveAnchor)
        line_start_pos = qt_cursor.position()
        qt_cursor.movePosition(MOVE.EndOfBlock, MODE.KeepAnchor)
        line_text = qt_cursor.selectedText()

        # Find first non-whitespace character
        first_non_ws = len(line_text) - len(line_text.lstrip())
        first_non_ws_pos = line_start_pos + first_non_ws

        # Reset cursor to original position
        qt_cursor.setPosition(state.anchor)
        if select or state.hasSelection():
            qt_cursor.setPosition(state.position, MODE.KeepAnchor)
        else:
            qt_cursor.setPosition(state.position)

        # Determine target position
        current_pos = state.position
        if current_pos == first_non_ws_pos or first_non_ws_pos == line_start_pos:
            # Already at first non-whitespace or line is all whitespace: go to column 0
            target_pos = line_start_pos
        else:
            # Go to first non-whitespace
            target_pos = first_non_ws_pos

        # Move to target
        mode = MODE.KeepAnchor if select else MODE.MoveAnchor
        qt_cursor.setPosition(target_pos, mode)
        return CursorState(qt_cursor.anchor(), qt_cursor.position())

    def move_cursors(
        self,
        direction: Union[QtCore.Qt.Key, int],
        select: bool = False,
        word_mode: bool = False,
    ):
        """Move all cursors in direction

        Args:
            direction: 'left', 'right', 'up', 'down', 'home', 'end'
            select: If True, extend selection (Shift+arrow)
            word_mode: If True, move by word (Ctrl+arrow) or document start/end for home/end
        """
        MOVE = QtGui.QTextCursor.MoveOperation
        MODE = QtGui.QTextCursor.MoveMode
        KEY = QtCore.Qt.Key

        if direction not in [
            KEY.Key_Left,
            KEY.Key_Right,
            KEY.Key_Up,
            KEY.Key_Down,
            KEY.Key_Home,
            KEY.Key_End,
        ]:
            return False

        mode = MODE.KeepAnchor if select else MODE.MoveAnchor

        cursors, _primary_index = self.get_all_cursors()

        new_cursors = []
        for state in cursors:
            # Determine move operation
            if direction == KEY.Key_Left:
                move_op = MOVE.WordLeft if word_mode else MOVE.Left
            elif direction == KEY.Key_Right:
                move_op = MOVE.WordRight if word_mode else MOVE.Right
            elif direction == KEY.Key_Up:
                move_op = MOVE.Up
            elif direction == KEY.Key_Down:
                move_op = MOVE.Down
            elif direction == KEY.Key_Home:
                if word_mode:
                    move_op = MOVE.Start
                else:
                    # Smart Home: toggle between first non-whitespace and column 0
                    qt_cursor = QtGui.QTextCursor(self.document())
                    state.apply(qt_cursor)
                    new_cursors.append(self._smart_home(qt_cursor, state, select))
                    continue
            elif direction == KEY.Key_End:
                move_op = MOVE.End if word_mode else MOVE.EndOfLine

            qt_cursor = QtGui.QTextCursor(self.document())
            state.apply(qt_cursor)
            qt_cursor.movePosition(move_op, mode)
            new_cursors.append(CursorState(qt_cursor.anchor(), qt_cursor.position()))

        # Update all cursors (this will merge if needed)
        self._set_all_cursors(new_cursors)
        return True

    def copy(self):
        """Copy text from all cursors to clipboard (joined with newlines)"""
        all_cursors, _primary_index = self.get_all_cursors()

        # Collect selected text from all cursors
        selected_texts = []
        qt_cursor = self.textCursor()

        for cursor_state in all_cursors:
            qt_cursor.setPosition(cursor_state.anchor)
            qt_cursor.setPosition(
                cursor_state.position, QtGui.QTextCursor.MoveMode.KeepAnchor
            )
            selected_text = qt_cursor.selectedText()
            selected_texts.append(selected_text)

        # Join all selections with a special separator
        # We use a marker that's unlikely to appear in normal text
        clipboard_text = "\n".join(selected_texts)

        # Store both the joined text and the count of selections
        clipboard = QtWidgets.QApplication.clipboard()
        mimeData = QtCore.QMimeData()

        lens = ",".join(map(str, map(len, selected_texts)))
        mimeData.setData(MIME, lens.encode())
        mimeData.setText(clipboard_text)
        clipboard.setMimeData(mimeData)

        # Store the length of the copy value per selection
        self._clipboard_cursor_counts = list(map(len, selected_texts))

    def cut(self):
        """Cut text from all cursors to clipboard"""
        self.copy()
        for cursor, is_primary in self.citer.iterate_cursors():
            if cursor.hasSelection():
                self.citer.update_offset(
                    cursor.selectionStart() - cursor.selectionEnd()
                )
                cursor.removeSelectedText()
            self.citer.cursor_completed()

    def paste(self):
        """Paste clipboard text at all cursor positions"""
        clipboard = QtWidgets.QApplication.clipboard()
        mimeData = clipboard.mimeData()
        clipboard_text = mimeData.text()
        if not clipboard_text:
            return

        if not mimeData.hasFormat(MIME):
            self.insert_text(clipboard_text)
            return

        copylen_text = bytes(mimeData.data(MIME)).decode()
        lens = list(map(int, copylen_text.split(",")))

        # Check that the number of cursors and the number of paste lines matches
        if len(self.secondary_cursors) + 1 != len(lens):
            self.insert_text(clipboard_text)
            return

        # Get how long we expect the text to be based on the copy
        # This is the copy lengths, plus all the separating newlines
        expected_len = sum(lens) + len(lens) - 1
        if len(clipboard_text) != expected_len:
            self.insert_text(clipboard_text)
            return

        lines = []
        ptr = 0
        for el in lens:
            lines.append(clipboard_text[ptr : ptr + el])
            ptr += el + 1  # skip the newlines

        for i, (cursor, is_primary) in enumerate(self.citer.iterate_cursors()):
            line = lines[i]
            cursor.insertText(line)
            self.citer.update_offset(len16(line))
            self.citer.cursor_completed()

    def add_cursor_above(self):
        """Add a new cursor on the line above the primary cursor (primary moves up, leaves cursor behind)"""
        # Get current cursor position - use primary cursor
        primary = self.get_primary_cursor()
        current_position = primary.position

        # Get current block and column
        doc = self.document()
        block = doc.findBlock(current_position)
        if not block.isValid():
            return

        # Move to previous block
        previous_block = block.previous()
        if not previous_block.isValid():
            return

        # Calculate column position
        col = min(current_position - block.position(), len16(previous_block.text()))

        # Position in previous line (this will be the new primary)
        new_primary_pos = previous_block.position() + col

        self.secondary_cursors.append(CursorState(current_position, current_position))
        new_primary = CursorState(new_primary_pos, new_primary_pos)
        self.set_primary_cursor(new_primary)
        self._render_cursors()

    def add_cursor_below(self):
        """Add a new cursor on the line below the primary cursor (primary moves down, leaves cursor behind)"""
        # Get current cursor position - use primary cursor
        primary = self.get_primary_cursor()
        current_position = primary.position

        # Get current block and column
        doc = self.document()
        block = doc.findBlock(current_position)
        if not block.isValid():
            return

        # Move to next block
        next_block = block.next()
        if not next_block.isValid():
            return

        # Calculate column position
        col = min(current_position - block.position(), len16(next_block.text()))

        # Position in next line (this will be the new primary)
        new_primary_pos = next_block.position() + col

        self.secondary_cursors.append(CursorState(current_position, current_position))

        new_primary = CursorState(new_primary_pos, new_primary_pos)
        self.set_primary_cursor(new_primary)
        self._render_cursors()

    def add_cursors_to_line_ends(self):
        """Add a cursor at the end of each line in the current selection"""
        cursor = self.textCursor()

        if not cursor.hasSelection():
            return

        # Get the selection range
        start = min(cursor.anchor(), cursor.position())
        end = max(cursor.anchor(), cursor.position())

        # Find all blocks in the selection
        doc = self.document()
        start_block = doc.findBlock(start)
        end_block = doc.findBlock(end)

        if not start_block.isValid() or not end_block.isValid():
            return

        # Collect cursor positions at the end of each line
        cursors = []
        block = start_block
        while block.isValid():
            # Add cursor at end of this line
            line_end = block.position() + len16(block.text())
            cursors.append(CursorState(line_end, line_end))

            if block == end_block:
                break
            block = block.next()

        if not cursors:
            return
        # Enter multi-cursor mode with these cursors
        new_primary = cursors[0]
        self.secondary_cursors = cursors[1:]
        # Update the visual Qt cursor to the primary position
        self.set_primary_cursor(new_primary)
        self._render_cursors()

    def add_cursor_at_position(self, position: int) -> bool:
        """Add a cursor at the specified position (for Alt+Click)"""
        # Add the new cursor at the clicked position
        new_cursor = CursorState(position, position)
        all_cursors, _primary_index = self.get_all_cursors()
        all_cursors.append(new_cursor)
        self._set_all_cursors(all_cursors)

        return True
