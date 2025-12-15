from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from Qt import QtCore, QtGui
from Qt.QtGui import QTextCursor, QColor
from Qt.QtWidgets import QTextEdit

if TYPE_CHECKING:
    from .line_editor import CodeEditor


@dataclass
class CursorState:
    """Represents a single cursor's position and selection"""
    anchor: int  # UTF-16 position
    position: int  # UTF-16 position

    @property
    def has_selection(self) -> bool:
        """Returns True if this cursor has a selection"""
        return self.anchor != self.position

    @property
    def selection_start(self) -> int:
        """Returns the start position of the selection (or cursor position if no selection)"""
        return min(self.anchor, self.position)

    @property
    def selection_end(self) -> int:
        """Returns the end position of the selection (or cursor position if no selection)"""
        return max(self.anchor, self.position)

    def __eq__(self, other) -> bool:
        if not isinstance(other, CursorState):
            return False
        return self.anchor == other.anchor and self.position == other.position

    def __hash__(self) -> int:
        return hash((self.anchor, self.position))


class MultiCursorManager:
    """Manages multiple cursors for simultaneous editing

    This manager coordinates multiple cursor positions and applies operations
    to all of them atomically. It uses Qt's single primary cursor and tracks
    additional cursors as positions, rendering them via ExtraSelections.
    """

    def __init__(self, editor: CodeEditor):
        self.editor = editor
        self.secondary_cursors: list[CursorState] = []
        self.active: bool = False  # Multi-cursor mode enabled?

        # Visual appearance
        self.primary_cursor_color = QColor(255, 255, 255, 255)  # White, fully opaque
        self.secondary_cursor_color = QColor(180, 180, 180, 200)  # Dimmed gray

        # Blinking
        self.blink_timer = QtCore.QTimer()
        self.blink_timer.timeout.connect(self._toggle_blink)
        self.blink_visible = True
        self.blink_interval = 500  # ms

    def is_active(self) -> bool:
        """Returns True if multi-cursor mode is active with secondary cursors"""
        return self.active and len(self.secondary_cursors) > 0

    def get_primary_cursor(self) -> CursorState:
        """Convert Qt's primary cursor to CursorState"""
        cursor = self.editor.textCursor()
        return CursorState(cursor.anchor(), cursor.position())

    def set_primary_cursor(self, state: CursorState):
        """Update Qt's primary cursor from CursorState"""
        cursor = self.editor.textCursor()
        cursor.setPosition(state.anchor)
        cursor.setPosition(state.position, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def get_all_cursors(self) -> list[CursorState]:
        """Return primary + all secondary cursors sorted by position"""
        all_cursors = [self.get_primary_cursor()] + self.secondary_cursors
        return sorted(all_cursors, key=lambda c: c.selection_start)

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
        self.active = len(self.secondary_cursors) > 0

        self._update_visual()

    def _merge_overlapping_cursors(self, cursors: list[CursorState]) -> list[CursorState]:
        """Merge cursors that overlap or are adjacent"""
        if len(cursors) <= 1:
            return cursors

        # Sort by start position
        cursors = sorted(cursors, key=lambda c: c.selection_start)

        merged = [cursors[0]]
        for cursor in cursors[1:]:
            last = merged[-1]

            # Check for overlap or adjacency
            if cursor.selection_start <= last.selection_end:
                # Merge: extend the last cursor
                new_anchor = min(last.anchor, cursor.anchor)
                new_position = max(last.position, cursor.position)
                merged[-1] = CursorState(new_anchor, new_position)
            else:
                merged.append(cursor)

        return merged

    def _update_visual(self):
        """Update visual rendering of secondary cursors"""
        if not self.is_active():
            self.editor.selection_manager.clear_selections("multi_cursor")
            self.blink_timer.stop()
            return

        # Start blinking timer if not already running
        if not self.blink_timer.isActive():
            self.blink_visible = True
            self.blink_timer.start(self.blink_interval)

        self._render_cursors()

    def _render_cursors(self):
        """Render secondary cursors as ExtraSelections"""
        if not self.blink_visible:
            self.editor.selection_manager.clear_selections("multi_cursor")
            return

        selections = []
        for cursor_state in self.secondary_cursors:
            # Create a QTextCursor for this position
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(cursor_state.anchor)
            cursor.setPosition(cursor_state.position, QTextCursor.MoveMode.KeepAnchor)

            # Create ExtraSelection
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor

            # Format for the cursor/selection
            fmt = QtGui.QTextCharFormat()

            if cursor_state.has_selection:
                # Selection background
                fmt.setBackground(self.secondary_cursor_color.lighter(150))
            else:
                # Cursor line (make it visible as a thin line)
                fmt.setBackground(self.secondary_cursor_color)

            selection.format = fmt
            selections.append(selection)

        self.editor.selection_manager.set_selections("multi_cursor", selections)

    def _toggle_blink(self):
        """Toggle cursor blink visibility"""
        self.blink_visible = not self.blink_visible
        self._render_cursors()

    def exit_multi_cursor_mode(self):
        """Exit multi-cursor mode, keep only primary cursor"""
        self.secondary_cursors.clear()
        self.active = False
        self.blink_timer.stop()
        self.editor.selection_manager.clear_selections("multi_cursor")

    def add_next_occurrence(self) -> bool:
        """Add cursor at next occurrence of current selection

        Returns True if a cursor was added, False otherwise
        """
        primary = self.get_primary_cursor()

        # Get search text from primary cursor selection
        if not primary.has_selection:
            # No selection - select word under cursor first
            if not self._select_word_under_cursor():
                return False
            primary = self.get_primary_cursor()

        search_text = self._get_text(primary.selection_start, primary.selection_end)
        if not search_text:
            return False

        # Find next occurrence after the last cursor
        all_cursors = self.get_all_cursors()
        search_start = all_cursors[-1].selection_end

        next_pos = self._find_next(search_text, search_start)

        if next_pos >= 0:
            # Add new secondary cursor at match
            new_cursor = CursorState(next_pos, next_pos + len(search_text))
            self.secondary_cursors.append(new_cursor)
            self.active = True
            self._update_visual()
            return True
        else:
            # Wrap around to beginning
            next_pos = self._find_next(search_text, 0)
            if next_pos >= 0 and next_pos < all_cursors[0].selection_start:
                new_cursor = CursorState(next_pos, next_pos + len(search_text))
                self.secondary_cursors.append(new_cursor)
                self.active = True
                self._update_visual()
                return True

        return False

    def _select_word_under_cursor(self) -> bool:
        """Select the word under the primary cursor

        Returns True if a word was selected, False otherwise
        """
        cursor = self.editor.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)

        if cursor.hasSelection():
            self.editor.setTextCursor(cursor)
            return True
        return False

    def _get_text(self, start: int, end: int) -> str:
        """Get text from document between positions"""
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText()

    def _find_next(self, search_text: str, start_pos: int) -> int:
        """Find next occurrence of search_text starting from start_pos

        Returns position of match, or -1 if not found
        """
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(start_pos)

        # Use document's find method
        found = self.editor.document().find(search_text, cursor)

        if not found.isNull():
            return found.selectionStart()
        return -1

    def handle_key_event(self, event: QtGui.QKeyEvent) -> bool:
        """Handle key events for multi-cursor mode

        Returns True if the event was handled, False otherwise
        """
        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        # Exit on Escape
        if key == QtCore.Qt.Key.Key_Escape:
            self.exit_multi_cursor_mode()
            return True

        # Handle printable characters (typing)
        if text and text.isprintable() and modifiers in (
            QtCore.Qt.KeyboardModifier.NoModifier,
            QtCore.Qt.KeyboardModifier.ShiftModifier,
        ):
            self.insert_text(text)
            return True

        # Handle special keys
        if key == QtCore.Qt.Key.Key_Backspace:
            if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
                self.delete_word_backward()
            else:
                self.backspace()
            return True

        if key == QtCore.Qt.Key.Key_Delete:
            if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
                self.delete_word_forward()
            else:
                self.delete_char()
            return True

        # Handle arrow keys
        select = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        word_mode = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)

        if key == QtCore.Qt.Key.Key_Left:
            self.move_cursors('left', select, word_mode)
            return True
        elif key == QtCore.Qt.Key.Key_Right:
            self.move_cursors('right', select, word_mode)
            return True
        elif key == QtCore.Qt.Key.Key_Up:
            self.move_cursors('up', select, word_mode)
            return True
        elif key == QtCore.Qt.Key.Key_Down:
            self.move_cursors('down', select, word_mode)
            return True

        # Handle Tab
        if key == QtCore.Qt.Key.Key_Tab:
            self.insert_text('\t')
            return True

        # Handle Return/Enter
        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            # Will be handled by smart_indent behavior if integrated
            return False

        return False

    def insert_text(self, text: str):
        """Insert text at all cursor positions"""
        cursors = self.get_all_cursors()

        # Sort reverse for insertions (back to front prevents position shifts)
        cursors.sort(key=lambda c: c.selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        for cursor in cursors:
            qt_cursor.setPosition(cursor.anchor)
            qt_cursor.setPosition(cursor.position, QTextCursor.MoveMode.KeepAnchor)

            # Delete selection if exists, then insert
            qt_cursor.insertText(text)

            # Track new position (cursor is after inserted text)
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Reverse to get original order (we edited in reverse)
        new_positions.reverse()
        self._set_all_cursors(new_positions)

    def backspace(self):
        """Delete character before cursor at all positions"""
        cursors = self.get_all_cursors()
        cursors.sort(key=lambda c: c.selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        for cursor in cursors:
            qt_cursor.setPosition(cursor.position)
            if cursor.has_selection:
                # Delete selection
                qt_cursor.setPosition(cursor.anchor, QTextCursor.MoveMode.KeepAnchor)
                qt_cursor.removeSelectedText()
            else:
                # Delete previous character
                qt_cursor.deletePreviousChar()

            # Track new position
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Reverse to get original order
        new_positions.reverse()
        self._set_all_cursors(new_positions)

    def delete_char(self):
        """Delete character at cursor at all positions"""
        cursors = self.get_all_cursors()
        cursors.sort(key=lambda c: c.selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        for cursor in cursors:
            qt_cursor.setPosition(cursor.position)
            if cursor.has_selection:
                # Delete selection
                qt_cursor.setPosition(cursor.anchor, QTextCursor.MoveMode.KeepAnchor)
                qt_cursor.removeSelectedText()
            else:
                # Delete next character
                qt_cursor.deleteChar()

            # Track new position
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Reverse to get original order
        new_positions.reverse()
        self._set_all_cursors(new_positions)

    def delete_word_forward(self):
        """Delete word forward from cursor at all positions"""
        cursors = self.get_all_cursors()
        cursors.sort(key=lambda c: c.selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        for cursor in cursors:
            qt_cursor.setPosition(cursor.position)
            if cursor.has_selection:
                # Delete selection
                qt_cursor.setPosition(cursor.anchor, QTextCursor.MoveMode.KeepAnchor)
                qt_cursor.removeSelectedText()
            else:
                # Delete to end of word
                qt_cursor.movePosition(QTextCursor.MoveOperation.EndOfWord, QTextCursor.MoveMode.KeepAnchor)
                qt_cursor.removeSelectedText()

            # Track new position
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Reverse to get original order
        new_positions.reverse()
        self._set_all_cursors(new_positions)

    def delete_word_backward(self):
        """Delete word backward from cursor at all positions"""
        cursors = self.get_all_cursors()
        cursors.sort(key=lambda c: c.selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        for cursor in cursors:
            qt_cursor.setPosition(cursor.position)
            if cursor.has_selection:
                # Delete selection
                qt_cursor.setPosition(cursor.anchor, QTextCursor.MoveMode.KeepAnchor)
                qt_cursor.removeSelectedText()
            else:
                # Delete to start of word
                qt_cursor.movePosition(QTextCursor.MoveOperation.StartOfWord, QTextCursor.MoveMode.KeepAnchor)
                qt_cursor.removeSelectedText()

            # Track new position
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Reverse to get original order
        new_positions.reverse()
        self._set_all_cursors(new_positions)

    def move_cursors(self, direction: str, select: bool = False, word_mode: bool = False):
        """Move all cursors in direction

        Args:
            direction: 'left', 'right', 'up', 'down'
            select: If True, extend selection (Shift+arrow)
            word_mode: If True, move by word (Ctrl+arrow)
        """
        cursors = self.get_all_cursors()

        new_cursors = []
        for cursor in cursors:
            qt_cursor = QTextCursor(self.editor.document())
            qt_cursor.setPosition(cursor.anchor)
            if select or cursor.has_selection:
                qt_cursor.setPosition(cursor.position, QTextCursor.MoveMode.KeepAnchor)
            else:
                qt_cursor.setPosition(cursor.position)

            # Determine move operation
            if direction == 'left':
                move_op = QTextCursor.MoveOperation.WordLeft if word_mode else QTextCursor.MoveOperation.Left
            elif direction == 'right':
                move_op = QTextCursor.MoveOperation.WordRight if word_mode else QTextCursor.MoveOperation.Right
            elif direction == 'up':
                move_op = QTextCursor.MoveOperation.Up
            elif direction == 'down':
                move_op = QTextCursor.MoveOperation.Down
            else:
                continue

            # Move cursor
            mode = QTextCursor.MoveMode.KeepAnchor if select else QTextCursor.MoveMode.MoveAnchor
            qt_cursor.movePosition(move_op, mode)

            new_cursors.append(CursorState(qt_cursor.anchor(), qt_cursor.position()))

        # Update all cursors (this will merge if needed)
        self._set_all_cursors(new_cursors)
