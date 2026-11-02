from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from Qt import QtGui

from .state import CursorState, primary_first

if TYPE_CHECKING:
    from ..code_editor import CodeEditor
    from .tracked import TrackedCursor


class CursorIterator:
    """Runs an edit at every cursor, in document order, as one undo step

    Each pass of `iterate_cursors` moves a single cursor to each cursor state.
    Every state follows the edits made at the other cursors, the way a
    QTextCursor does.

    A pass can mark a cursor as completed, and later passes in the same
    `session` skip it. That lets behaviors handle some cursors and leave the
    rest to the next handler. Replacing the editor's cursors during a session
    starts over with the new cursors, none of them completed, and ends the
    pass that replaced them.
    """

    def __init__(self, editor: CodeEditor) -> None:
        self.editor = editor
        # Whether the cursor being yielded was marked completed
        self._current_completed = False
        # The cursors of the session, and whether each one is completed
        self._states: list[CursorState] = []
        self._completed: list[bool] = []
        self._primary_index: int = 0
        # Set while a pass writes its cursors back, which isn't a replacement
        self._writing_back = False
        self.active = False
        editor.cursors.changed.connect(self._on_cursors_changed)

    def snapshot_cursors(self) -> None:
        """Take the editor's current cursors, and clear their completed flags"""
        self._states, self._primary_index = self.editor.cursors.in_document_order()
        self._completed = [False] * len(self._states)

    def _on_cursors_changed(self) -> None:
        if self.active and not self._writing_back:
            self.snapshot_cursors()

    @contextmanager
    def session(self) -> Iterator[None]:
        """Run several iterate_cursors passes as a single operation

        The cursors are snapshot once at the start, and any cursor completed
        by one pass is skipped by the passes after it
        """
        self.snapshot_cursors()
        self.active = True
        try:
            yield
        finally:
            self.active = False

    def mark_cursor_completed(self) -> None:
        """Mark the current cursor as completed. Only useful inside iterate_cursors"""
        self._current_completed = True

    def all_completed(self) -> bool:
        """Whether every cursor in the current session has been completed"""
        return all(self._completed)

    def read_cursors(self) -> Iterator[QtGui.QTextCursor]:
        """Yield a cursor at each non-completed cursor state, to read the document

        These are in the same order as `iterate_cursors`, but moving them doesn't
        move the editor's cursors, and editing with them isn't tracked
        """
        if not self.active:
            self.snapshot_cursors()
        qt_cursor = QtGui.QTextCursor(self.editor.document())
        for state, completed in zip(self._states, self._completed):
            if not completed:
                yield state.apply(qt_cursor)

    def iterate_cursors(
        self, join_edit: bool = False, complete_all: bool = False
    ) -> Iterator[TrackedCursor]:
        """Yield a cursor at each non-completed cursor state, in one edit block

        Args:
            join_edit: Join the edits onto the previous undo step
            complete_all: Mark every yielded cursor completed, for a pass that
                handles every cursor
        """
        if not self.active:
            # A one-off edit outside of a session works on the current cursors
            self.snapshot_cursors()
        states, completed = self._states, self._completed

        document = self.editor.document()
        qt_cursor = self.editor.textCursor()
        # Qt moves these with every edit, even one that deletes past them, so
        # they always hold where each cursor is now
        trackers = [state.build_cursor(document) for state in states]
        if join_edit:
            qt_cursor.joinPreviousEditBlock()
        else:
            qt_cursor.beginEditBlock()

        yielded_any = False
        try:
            for i, tracker in enumerate(trackers):
                if completed[i]:
                    continue

                CursorState.from_cursor(tracker).apply(qt_cursor)
                self._current_completed = False
                yield qt_cursor
                if self._states is not states:
                    # The loop body replaced the cursors, so the old ones are stale
                    return
                CursorState.from_cursor(qt_cursor).apply(tracker)
                completed[i] = complete_all or self._current_completed
                yielded_any = True
        finally:
            qt_cursor.endEditBlock()
            # Later edits can move the cursors before them too
            if self._states is states:
                for state, tracker in zip(states, trackers):
                    state.copy_from(tracker)

        if yielded_any:
            self._writing_back = True
            try:
                self.editor.cursors.replace_all(
                    primary_first(self._states, self._primary_index)
                )
            finally:
                self._writing_back = False
