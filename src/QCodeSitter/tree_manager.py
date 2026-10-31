from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtCore
from tree_sitter import Language, Node, Parser, Point, Tree

from .constants import ENC

if TYPE_CHECKING:
    from Qt import QtWidgets


class TreeManager(QtCore.QObject):
    """Manages the tree-sitter parse tree with incremental updates

    This class owns the parse tree and provides a shared resource for both
    syntax highlighting and syntax analysis. It supports incremental updates
    to efficiently re-parse only the changed portions of the document.
    """

    reparsed = QtCore.Signal()

    def __init__(
        self,
        editor: QtWidgets.QPlainTextEdit,
        language: Language | None = None,
    ):
        """Initialize the tree manager

        Args:
            editor: The editor whose document provides the source text
            language: The tree-sitter Language to use for parsing
        """
        super().__init__()
        self.editor = editor
        self.parser: Parser | None = None
        self.tree: Tree | None = None
        self._paused = False
        self._pause_edit = False

        # The (first, last) rows touched by edits since the last parse
        self._edit_rows: tuple[int, int] | None = None
        # The (first, last) row ranges that changed in the last parse
        # None means the whole document changed
        self.changed_rows: list[tuple[int, int]] | None = None

        self.setLanguage(language)

    def setLanguage(self, language: Language | None):
        self.parser = Parser(language) if language is not None else None
        self.tree = None
        self._edit_rows = None
        self.changed_rows = None

    def treesitter_source_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """Provide source bytes to tree-sitter parser

        A callback for efficient access to the underlying UTF-16LE encoded data

        Args:
            byte_offset: The byte offset in UTF-16LE encoding where data is requested
            ts_point: The (row, column) point where data is requested

        Returns:
            UTF-16LE encoded bytes from the requested position to end of the line
        """
        curblock = self.editor.document().findBlockByNumber(ts_point.row)
        # The block can be invalid after an undo
        if not curblock.isValid():
            return b""

        suffix = "\n" if curblock.next().isValid() else ""
        linetext = curblock.text() + suffix

        # When using encoding='utf16', ts_point.column is in BYTES, not code units
        return linetext.encode(ENC)[ts_point.column :]

    def fullUpdate(self):
        if self.parser is not None:
            self.tree = self.parser.parse(
                self.treesitter_source_callback, encoding="utf16"
            )
            self._edit_rows = None
            self.changed_rows = None
            self.reparsed.emit()

    def pause(self):
        self._paused = True
        self._pause_edit = False

    def unpause(self):
        if not self._paused:
            return
        self._paused = False
        if self._pause_edit:
            self.reparse()

    def _track_edit_rows(self, start_row: int, old_end_row: int, new_end_row: int):
        """Grow the span of edited rows to include this edit

        The span is kept in the current document's rows, so rows after
        the edit shift by the number of lines it added or removed
        """
        if self._edit_rows is None:
            self._edit_rows = (start_row, new_end_row)
            return
        lo, hi = self._edit_rows
        if hi > old_end_row:
            hi += new_end_row - old_end_row
        else:
            hi = new_end_row
        self._edit_rows = (min(lo, start_row), hi)

    def update(
        self,
        start_byte: int,
        old_end_byte: int,
        new_end_byte: int,
        start_point: Point,
        old_end_point: Point,
        new_end_point: Point,
    ) -> Tree | None:
        """Incrementally update the parse tree after document changes

        Args:
            start_byte: UTF-16 code unit offset where the change started
            old_end_byte: UTF-16 code unit offset where the change ended (before change)
            new_end_byte: UTF-16 code unit offset where the change ends (after change)
            start_point: (row, column) where the change started (column in UTF-16 code units)
            old_end_point: (row, column) where the change ended (before change)
            new_end_point: (row, column) where the change ends (after change)
        """
        if self.tree is not None:
            self.tree.edit(
                start_byte=start_byte,
                old_end_byte=old_end_byte,
                new_end_byte=new_end_byte,
                start_point=start_point,
                old_end_point=old_end_point,
                new_end_point=new_end_point,
            )
        self._track_edit_rows(start_point.row, old_end_point.row, new_end_point.row)
        return self.reparse()

    def reparse(self) -> Tree | None:
        if self._paused:
            self._pause_edit = True
            return self.tree

        old_tree = self.tree
        if self.parser is None:
            self._edit_rows = None
            return old_tree

        if old_tree is None:
            self.tree = self.parser.parse(
                self.treesitter_source_callback, encoding="utf16"
            )
            self.changed_rows = None
        else:
            self.tree = self.parser.parse(
                self.treesitter_source_callback, old_tree, encoding="utf16"
            )
            # The rows that need rehighlighting are the ones whose syntax changed
            # plus the ones that were edited, because predicates check the text
            rows = [
                (r.start_point.row, r.end_point.row)
                for r in old_tree.changed_ranges(self.tree)
            ]
            if self._edit_rows is not None:
                rows.append(self._edit_rows)
            self.changed_rows = rows
        self._edit_rows = None
        self.reparsed.emit()
        return old_tree

    def get_node_at_point(self, byte_offset: int) -> Node | None:
        """Get the AST node at a specific UTF-16 code unit offset

        Args:
            byte_offset: The UTF-16 code unit offset in the document

        Returns:
            The tree-sitter Node at the given offset, or None if no tree exists
        """
        if self.tree is None:
            return None
        return self.tree.root_node.descendant_for_byte_range(byte_offset, byte_offset)

    @property
    def root_node(self) -> Node | None:
        """Get the root node of the parse tree

        Returns:
            The root Node of the tree, or None if no tree exists
        """
        return self.tree.root_node if self.tree else None
