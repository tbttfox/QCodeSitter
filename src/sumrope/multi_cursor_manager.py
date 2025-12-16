from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from Qt import QtCore, QtGui
from Qt.QtGui import QTextCursor, QColor
from Qt.QtWidgets import QTextEdit, QApplication

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

        doc = self.editor.document()
        max_pos = doc.characterCount()

        selections = []
        for cursor_state in self.secondary_cursors:
            # Validate cursor position is within document bounds
            if cursor_state.position < 0 or cursor_state.position > max_pos:
                continue  # Skip invalid cursor
            if cursor_state.anchor < 0 or cursor_state.anchor > max_pos:
                continue  # Skip invalid cursor

            # Create a QTextCursor for this position
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(min(cursor_state.anchor, max_pos))
            cursor.setPosition(min(cursor_state.position, max_pos), QTextCursor.MoveMode.KeepAnchor)

            # Create ExtraSelection
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor

            # Format for the cursor/selection
            fmt = QtGui.QTextCharFormat()

            if cursor_state.has_selection:
                # Selection background
                fmt.setBackground(self.secondary_cursor_color.lighter(150))
            else:
                # For cursor positions (no selection), we need to select one character
                # to make it visible. If at end of line, select the newline.
                # If at end of document, select backwards one char.
                if cursor_state.position < max_pos - 1:
                    # Select next character
                    cursor.setPosition(cursor_state.position)
                    cursor.setPosition(cursor_state.position + 1, QTextCursor.MoveMode.KeepAnchor)
                elif cursor_state.position > 0 and cursor_state.position <= max_pos:
                    # At end - select previous character
                    cursor.setPosition(cursor_state.position - 1)
                    cursor.setPosition(min(cursor_state.position, max_pos), QTextCursor.MoveMode.KeepAnchor)

                selection.cursor = cursor
                # Use underline to show cursor position
                fmt.setBackground(self.secondary_cursor_color)
                fmt.setForeground(QColor(0, 0, 0))  # Black text on gray background

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
        # But let auto-bracket behavior handle bracket/quote characters
        if text and text.isprintable() and modifiers in (
            QtCore.Qt.KeyboardModifier.NoModifier,
            QtCore.Qt.KeyboardModifier.ShiftModifier,
        ):
            # Let auto-bracket behavior handle these characters
            if text in '([{"\'`)]}"\'`':
                return False
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

        # Handle arrow keys (but not Ctrl+Alt+Up/Down - those are for adding cursors)
        if modifiers & QtCore.Qt.KeyboardModifier.AltModifier:
            # Let Alt+arrow combinations be handled by hotkeys
            return False

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

        # Handle Copy (Ctrl+C)
        if key == QtCore.Qt.Key.Key_C and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.copy()
            return True

        # Handle Paste (Ctrl+V)
        if key == QtCore.Qt.Key.Key_V and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.paste()
            return True

        # Handle Cut (Ctrl+X)
        if key == QtCore.Qt.Key.Key_X and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.cut()
            return True

        return False

    def insert_text(self, text: str):
        """Insert text at all cursor positions"""
        primary = self.get_primary_cursor()
        all_cursors = self.get_all_cursors()

        # Sort reverse for insertions (back to front prevents position shifts)
        # But keep track of which one was primary
        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None

        for cursor, original_index in sorted_with_index:
            # Check if this is the primary cursor
            if cursor == primary:
                primary_index = len(new_positions)

            qt_cursor.setPosition(cursor.anchor)
            qt_cursor.setPosition(cursor.position, QTextCursor.MoveMode.KeepAnchor)

            # Delete selection if exists, then insert
            qt_cursor.insertText(text)

            # Track new position (cursor is after inserted text)
            # Don't apply any offset yet - we'll adjust all positions after we're done
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Now adjust all positions to account for the length changes
        # new_positions = [later_pos, earlier_pos, ...] (reverse doc order)
        # We iterate backwards and accumulate offsets for earlier positions
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):  # Iterate backwards
            pos = new_positions[i]
            # This position needs to be adjusted by all the edits that happened AFTER it (earlier in the loop)
            adjusted_pos = CursorState(pos.anchor + cumulative_offset, pos.position + cumulative_offset)
            adjusted_positions.insert(0, adjusted_pos)  # Insert at front to build in document order

            # Calculate the length change that THIS edit caused
            original_cursor = sorted_with_index[i][0]
            selection_length = abs(original_cursor.position - original_cursor.anchor)
            length_change = len(text) - selection_length
            cumulative_offset += length_change

        new_positions = adjusted_positions

        # Adjust primary index after reversal
        if primary_index is not None:
            primary_index = len(new_positions) - 1 - primary_index

        # Set primary cursor explicitly
        if primary_index is not None and primary_index < len(new_positions):
            # Move primary to front
            primary_cursor = new_positions.pop(primary_index)
            new_positions.insert(0, primary_cursor)

        self._set_all_cursors(new_positions)

    def backspace(self):
        """Delete character before cursor at all positions"""
        primary = self.get_primary_cursor()
        all_cursors = self.get_all_cursors()

        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None
        for cursor, original_index in sorted_with_index:
            if cursor == primary:
                primary_index = len(new_positions)

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

        # Now adjust all positions to account for the length changes
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):  # Iterate backwards
            pos = new_positions[i]
            adjusted_pos = CursorState(pos.anchor + cumulative_offset, pos.position + cumulative_offset)
            adjusted_positions.insert(0, adjusted_pos)

            # Calculate the length change that THIS deletion caused
            original_cursor = sorted_with_index[i][0]
            if original_cursor.has_selection:
                length_change = -(original_cursor.selection_end - original_cursor.selection_start)
            else:
                length_change = -1  # Deleted one character
            cumulative_offset += length_change

        new_positions = adjusted_positions

        # Adjust primary index and move to front
        if primary_index is not None:
            primary_index = len(new_positions) - 1 - primary_index
            if primary_index < len(new_positions):
                primary_cursor = new_positions.pop(primary_index)
                new_positions.insert(0, primary_cursor)

        self._set_all_cursors(new_positions)

    def delete_char(self):
        """Delete character at cursor at all positions"""
        primary = self.get_primary_cursor()
        all_cursors = self.get_all_cursors()

        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None
        for cursor, original_index in sorted_with_index:
            if cursor == primary:
                primary_index = len(new_positions)

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

        # Now adjust all positions to account for the length changes
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):  # Iterate backwards
            pos = new_positions[i]
            adjusted_pos = CursorState(pos.anchor + cumulative_offset, pos.position + cumulative_offset)
            adjusted_positions.insert(0, adjusted_pos)

            # Calculate the length change that THIS deletion caused
            original_cursor = sorted_with_index[i][0]
            if original_cursor.has_selection:
                length_change = -(original_cursor.selection_end - original_cursor.selection_start)
            else:
                length_change = -1  # Deleted one character
            cumulative_offset += length_change

        new_positions = adjusted_positions

        # Adjust primary index and move to front
        if primary_index is not None:
            primary_index = len(new_positions) - 1 - primary_index
            if primary_index < len(new_positions):
                primary_cursor = new_positions.pop(primary_index)
                new_positions.insert(0, primary_cursor)

        self._set_all_cursors(new_positions)

    def delete_word_forward(self):
        """Delete word forward from cursor at all positions"""
        primary = self.get_primary_cursor()
        all_cursors = self.get_all_cursors()

        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None
        deletion_lengths = []  # Track how much was deleted at each position

        for cursor, original_index in sorted_with_index:
            if cursor == primary:
                primary_index = len(new_positions)

            qt_cursor.setPosition(cursor.position)
            start_pos = cursor.position

            if cursor.has_selection:
                # Delete selection
                qt_cursor.setPosition(cursor.anchor, QTextCursor.MoveMode.KeepAnchor)
                deleted_length = cursor.selection_end - cursor.selection_start
                qt_cursor.removeSelectedText()
            else:
                # Delete to end of word
                qt_cursor.movePosition(QTextCursor.MoveOperation.EndOfWord, QTextCursor.MoveMode.KeepAnchor)
                deleted_length = qt_cursor.position() - start_pos
                qt_cursor.removeSelectedText()

            deletion_lengths.append(deleted_length)

            # Track new position
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Now adjust all positions to account for the length changes
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):  # Iterate backwards
            pos = new_positions[i]
            adjusted_pos = CursorState(pos.anchor + cumulative_offset, pos.position + cumulative_offset)
            adjusted_positions.insert(0, adjusted_pos)

            # Calculate the length change that THIS deletion caused
            length_change = -deletion_lengths[i]
            cumulative_offset += length_change

        new_positions = adjusted_positions

        # Adjust primary index and move to front
        if primary_index is not None:
            primary_index = len(new_positions) - 1 - primary_index
            if primary_index < len(new_positions):
                primary_cursor = new_positions.pop(primary_index)
                new_positions.insert(0, primary_cursor)

        self._set_all_cursors(new_positions)

    def delete_word_backward(self):
        """Delete word backward from cursor at all positions"""
        primary = self.get_primary_cursor()
        all_cursors = self.get_all_cursors()

        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None
        deletion_lengths = []  # Track how much was deleted at each position

        for cursor, original_index in sorted_with_index:
            if cursor == primary:
                primary_index = len(new_positions)

            qt_cursor.setPosition(cursor.position)
            start_pos = cursor.position

            if cursor.has_selection:
                # Delete selection
                qt_cursor.setPosition(cursor.anchor, QTextCursor.MoveMode.KeepAnchor)
                deleted_length = cursor.selection_end - cursor.selection_start
                qt_cursor.removeSelectedText()
            else:
                # Delete to start of word - calculate length BEFORE deleting
                qt_cursor.movePosition(QTextCursor.MoveOperation.StartOfWord, QTextCursor.MoveMode.KeepAnchor)
                # Calculate the selection length before removing
                deleted_length = abs(qt_cursor.position() - qt_cursor.anchor())
                qt_cursor.removeSelectedText()

            deletion_lengths.append(deleted_length)

            # Track new position
            new_pos = qt_cursor.position()
            new_positions.append(CursorState(new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Now adjust all positions to account for the length changes
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):  # Iterate backwards
            pos = new_positions[i]
            adjusted_pos = CursorState(pos.anchor + cumulative_offset, pos.position + cumulative_offset)
            adjusted_positions.insert(0, adjusted_pos)

            # Calculate the length change that THIS deletion caused
            length_change = -deletion_lengths[i]
            cumulative_offset += length_change

        new_positions = adjusted_positions

        # Adjust primary index and move to front
        if primary_index is not None:
            primary_index = len(new_positions) - 1 - primary_index
            if primary_index < len(new_positions):
                primary_cursor = new_positions.pop(primary_index)
                new_positions.insert(0, primary_cursor)

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

    def copy(self):
        """Copy text from all cursors to clipboard (joined with newlines)"""
        all_cursors = self.get_all_cursors()

        # Collect selected text from all cursors
        selected_texts = []
        qt_cursor = self.editor.textCursor()

        for cursor_state in all_cursors:
            qt_cursor.setPosition(cursor_state.anchor)
            qt_cursor.setPosition(cursor_state.position, QTextCursor.MoveMode.KeepAnchor)
            selected_text = qt_cursor.selectedText()
            selected_texts.append(selected_text)

        # Join all selections with a special separator
        # We use a marker that's unlikely to appear in normal text
        clipboard_text = "\n".join(selected_texts)

        # Store both the joined text and the count of selections
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)

        # Store the number of selections in a member variable for paste
        self._clipboard_cursor_count = len(selected_texts)

    def cut(self):
        """Cut text from all cursors to clipboard"""
        # First copy the text
        self.copy()

        # Then delete all selections
        primary = self.get_primary_cursor()
        all_cursors = self.get_all_cursors()

        # Sort reverse for deletions (back to front)
        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None

        for cursor_state, original_index in sorted_with_index:
            if cursor_state == primary:
                primary_index = len(new_positions)

            qt_cursor.setPosition(cursor_state.anchor)
            qt_cursor.setPosition(cursor_state.position, QTextCursor.MoveMode.KeepAnchor)

            if cursor_state.has_selection:
                qt_cursor.removeSelectedText()

            new_pos = qt_cursor.position()
            new_positions.append((new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Adjust positions for cumulative deletions
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):
            pos = new_positions[i]
            adjusted_pos = (pos[0] + cumulative_offset, pos[1] + cumulative_offset)
            adjusted_positions.insert(0, adjusted_pos)

            # Calculate the deletion length
            original_cursor = sorted_with_index[i][0]
            if original_cursor.has_selection:
                deletion_length = abs(original_cursor.position - original_cursor.anchor)
                cumulative_offset -= deletion_length

        # Adjust primary index and move to front
        if primary_index is not None:
            primary_index = len(adjusted_positions) - 1 - primary_index
            if primary_index < len(adjusted_positions):
                primary_cursor = adjusted_positions.pop(primary_index)
                adjusted_positions.insert(0, primary_cursor)

        # Update cursors
        cursor_states = [CursorState(anchor, pos) for anchor, pos in adjusted_positions]
        self._set_all_cursors(cursor_states)

    def paste(self):
        """Paste clipboard text at all cursor positions"""
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()

        if not clipboard_text:
            return

        # Check if we have multi-cursor clipboard data
        cursor_count = getattr(self, '_clipboard_cursor_count', None)
        all_cursors = self.get_all_cursors()

        # Split clipboard by newlines
        lines = clipboard_text.split('\n')

        # If the number of lines matches the number of cursors and we copied from multi-cursor
        if cursor_count and len(lines) == len(all_cursors) == cursor_count:
            # Paste each line to corresponding cursor
            self._paste_multi(lines)
        else:
            # Paste the whole clipboard content at each cursor
            self.insert_text(clipboard_text)

    def _paste_multi(self, texts: list[str]):
        """Paste different text at each cursor position"""
        primary = self.get_primary_cursor()
        all_cursors = self.get_all_cursors()

        # Sort reverse for insertions (back to front)
        sorted_with_index = [(c, i) for i, c in enumerate(all_cursors)]
        sorted_with_index.sort(key=lambda x: x[0].selection_start, reverse=True)

        qt_cursor = self.editor.textCursor()
        qt_cursor.beginEditBlock()

        new_positions = []
        primary_index = None

        for cursor_state, original_index in sorted_with_index:
            if cursor_state == primary:
                primary_index = len(new_positions)

            # Get the text for this cursor (in reverse order)
            text_index = len(sorted_with_index) - 1 - len(new_positions)
            text_to_insert = texts[text_index] if text_index < len(texts) else ""

            qt_cursor.setPosition(cursor_state.anchor)
            qt_cursor.setPosition(cursor_state.position, QTextCursor.MoveMode.KeepAnchor)
            qt_cursor.insertText(text_to_insert)

            new_pos = qt_cursor.position()
            new_positions.append((new_pos, new_pos))

        qt_cursor.endEditBlock()

        # Adjust positions
        adjusted_positions = []
        cumulative_offset = 0

        for i in range(len(new_positions) - 1, -1, -1):
            pos = new_positions[i]
            adjusted_pos = (pos[0] + cumulative_offset, pos[1] + cumulative_offset)
            adjusted_positions.insert(0, adjusted_pos)

            # Calculate the length change
            text_index = len(sorted_with_index) - 1 - i
            inserted_text = texts[text_index] if text_index < len(texts) else ""
            original_cursor = sorted_with_index[i][0]
            selection_length = abs(original_cursor.position - original_cursor.anchor)
            length_change = len(inserted_text) - selection_length
            cumulative_offset += length_change

        # Adjust primary index and move to front
        if primary_index is not None:
            primary_index = len(adjusted_positions) - 1 - primary_index
            if primary_index < len(adjusted_positions):
                primary_cursor = adjusted_positions.pop(primary_index)
                adjusted_positions.insert(0, primary_cursor)

        # Update cursors
        cursor_states = [CursorState(anchor, pos) for anchor, pos in adjusted_positions]
        self._set_all_cursors(cursor_states)

    def add_cursor_above(self) -> bool:
        """Add a new cursor on the line above the primary cursor (primary moves up, leaves cursor behind)"""
        # Get current cursor position - use primary cursor if already active
        if self.is_active():
            current_position = self.primary_cursor.position
        else:
            cursor = self.editor.textCursor()
            current_position = cursor.position()

        # Get current block and column
        doc = self.editor.document()
        block = doc.findBlock(current_position)
        if not block.isValid():
            return False

        # Move to previous block
        previous_block = block.previous()
        if not previous_block.isValid():
            return False

        # Calculate column position
        col = current_position - block.position()

        # Position in previous line (this will be the new primary)
        new_primary_pos = previous_block.position() + min(col, len(previous_block.text()))

        if not self.is_active():
            # Start multi-cursor mode
            # Primary cursor moves to the line above
            self.primary_cursor = CursorState(new_primary_pos, new_primary_pos)
            # Leave a cursor at the original position
            self.secondary_cursors = [CursorState(current_position, current_position)]
            self.active = True
            # Update the visual Qt cursor to the new primary position
            self.set_primary_cursor(self.primary_cursor)
            self._render_cursors()
        else:
            # Already in multi-cursor mode
            # Move primary to the line above and leave it behind as secondary
            old_primary = self.primary_cursor

            # Add old primary position to secondaries
            self.secondary_cursors.append(CursorState(current_position, current_position))

            # Set new primary
            self.primary_cursor = CursorState(new_primary_pos, new_primary_pos)
            # Update the visual Qt cursor to the new primary position
            self.set_primary_cursor(self.primary_cursor)
            self._render_cursors()

        return True

    def add_cursor_below(self) -> bool:
        """Add a new cursor on the line below the primary cursor (primary moves down, leaves cursor behind)"""
        # Get current cursor position - use primary cursor if already active
        if self.is_active():
            current_position = self.primary_cursor.position
        else:
            cursor = self.editor.textCursor()
            current_position = cursor.position()

        # Get current block and column
        doc = self.editor.document()
        block = doc.findBlock(current_position)
        if not block.isValid():
            return False

        # Move to next block
        next_block = block.next()
        if not next_block.isValid():
            return False

        # Calculate column position
        col = current_position - block.position()

        # Position in next line (this will be the new primary)
        new_primary_pos = next_block.position() + min(col, len(next_block.text()))

        if not self.is_active():
            # Start multi-cursor mode
            # Primary cursor moves to the line below
            self.primary_cursor = CursorState(new_primary_pos, new_primary_pos)
            # Leave a cursor at the original position
            self.secondary_cursors = [CursorState(current_position, current_position)]
            self.active = True
            # Update the visual Qt cursor to the new primary position
            self.set_primary_cursor(self.primary_cursor)
            self._render_cursors()
        else:
            # Already in multi-cursor mode
            # Move primary to the line below and leave it behind as secondary
            old_primary = self.primary_cursor

            # Add old primary position to secondaries
            self.secondary_cursors.append(CursorState(current_position, current_position))

            # Set new primary
            self.primary_cursor = CursorState(new_primary_pos, new_primary_pos)
            # Update the visual Qt cursor to the new primary position
            self.set_primary_cursor(self.primary_cursor)
            self._render_cursors()

        return True

    def add_cursors_to_line_ends(self) -> bool:
        """Add a cursor at the end of each line in the current selection"""
        cursor = self.editor.textCursor()

        if not cursor.hasSelection():
            return False

        # Get the selection range
        start = min(cursor.anchor(), cursor.position())
        end = max(cursor.anchor(), cursor.position())

        # Find all blocks in the selection
        doc = self.editor.document()
        start_block = doc.findBlock(start)
        end_block = doc.findBlock(end)

        if not start_block.isValid() or not end_block.isValid():
            return False

        # Collect cursor positions at the end of each line
        cursors = []
        block = start_block
        while block.isValid():
            # Add cursor at end of this line
            line_end = block.position() + len(block.text())
            cursors.append(CursorState(line_end, line_end))

            if block == end_block:
                break
            block = block.next()

        if cursors:
            # Enter multi-cursor mode with these cursors
            self.primary_cursor = cursors[0]
            self.secondary_cursors = cursors[1:]
            self._render_cursors()
            return True

        return False

    def add_cursor_at_position(self, position: int) -> bool:
        """Add a cursor at the specified position (for Alt+Click)"""
        if not self.is_active():
            # Start multi-cursor mode with current cursor
            cursor = self.editor.textCursor()
            self.primary_cursor = CursorState(cursor.anchor(), cursor.position())
            self.secondary_cursors = []

        # Add the new cursor at the clicked position
        new_cursor = CursorState(position, position)
        all_cursors = self.get_all_cursors()
        all_cursors.append(new_cursor)
        self._set_all_cursors(all_cursors)

        return True

