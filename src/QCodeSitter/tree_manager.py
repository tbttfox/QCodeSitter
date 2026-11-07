from __future__ import annotations

from Qt import QtCore
from tree_sitter import Language, Node, Parser, Point, Tree

from .tracked_document import ENC, TrackedDocument


class TreeManager(QtCore.QObject):
    """Owns the tree-sitter parse tree of a document

    Edits are applied incrementally, and every reparse emits `reparsed`.
    Offsets and Point columns are UTF-16LE bytes, see TrackedDocument.
    """

    reparsed = QtCore.Signal()
    # Emitted after the language changes, before the new tree is parsed
    languageChanged = QtCore.Signal()

    def __init__(self, document: TrackedDocument) -> None:
        super().__init__()
        self.document = document
        self.parser: Parser | None = None
        self.tree: Tree | None = None
        self._pause_depth = 0
        # Whether an edit was made while paused, so unpausing has to reparse
        self._reparse_pending = False

        # The (first, last) rows of each edit since the last parse
        self._edit_rows: list[tuple[int, int]] = []
        # The (first, last) row ranges that changed in the last parse
        # None means the whole document changed
        self.changed_rows: list[tuple[int, int]] | None = None

        self._set_parser(None)

    @property
    def language(self) -> Language | None:
        return self.parser.language if self.parser is not None else None

    @property
    def is_paused(self) -> bool:
        return self._pause_depth > 0

    @property
    def reparse_pending(self) -> bool:
        """Whether edits are held by a pause, and the tree is out of date"""
        return self._pause_depth > 0 and self._reparse_pending

    def set_language(self, language: Language | None) -> None:
        """Change the language, and parse the document again"""
        self._set_parser(language)
        self.languageChanged.emit()
        self.parse_from_scratch()

    def _set_parser(self, language: Language | None) -> None:
        self.parser = Parser(language) if language is not None else None
        self.tree = None
        self._edit_rows = []
        self.changed_rows = None

    def treesitter_source_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """Give tree-sitter the UTF-16LE bytes from a Point to the end of its line"""
        curblock = self.document.findBlockByNumber(ts_point.row)
        # The block can be invalid after an undo
        if not curblock.isValid():
            return b""

        suffix = "\n" if curblock.next().isValid() else ""
        linetext = curblock.text() + suffix
        return linetext.encode(ENC)[ts_point.column :]

    def _parse(self, parser: Parser, old_tree: Tree | None = None) -> Tree:
        if old_tree is None:
            return parser.parse(self.treesitter_source_callback, encoding="utf16")
        return parser.parse(self.treesitter_source_callback, old_tree, encoding="utf16")

    def parse_from_scratch(self) -> None:
        """Parse the whole document from scratch. Without a language there is no tree"""
        self.tree = self._parse(self.parser) if self.parser is not None else None
        self._edit_rows = []
        self.changed_rows = None
        self.reparsed.emit()

    def pause(self) -> None:
        """Hold reparses until `unpause`, so a group of edits is parsed once

        Pauses nest, and only the unpause matching the first pause reparses
        """
        if self._pause_depth == 0:
            self._reparse_pending = False
        self._pause_depth += 1

    def unpause(self) -> None:
        if self._pause_depth == 0:
            return
        self._pause_depth -= 1
        if self._pause_depth == 0 and self._reparse_pending:
            self._reparse_pending = False
            self.reparse()

    def _track_edit_rows(
        self, start_row: int, old_end_row: int, new_end_row: int
    ) -> None:
        """Add this edit's rows to the edited spans

        Spans are kept separate, so edits far apart (ie: multi-cursor) don't
        mark every row between them. They're kept in the current document's
        rows, so earlier spans shift by the lines this edit added or removed
        """
        delta = new_end_row - old_end_row

        def shift(row: int) -> int:
            if row > old_end_row:
                return row + delta
            # A row inside a removed range collapses to the edit's end
            return min(row, new_end_row) if row > start_row else row

        self._edit_rows = [(shift(lo), shift(hi)) for lo, hi in self._edit_rows]
        self._edit_rows.append((start_row, new_end_row))

    def apply_edit(
        self,
        start_byte: int,
        old_end_byte: int,
        new_end_byte: int,
        start_point: Point,
        old_end_point: Point,
        new_end_point: Point,
    ) -> None:
        """Apply a document edit to the tree and reparse

        The arguments match TrackedDocument.byteContentsChange: UTF-16LE byte
        offsets, and Points whose columns are in bytes
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
        self.reparse()

    def reparse(self) -> None:
        """Reparse incrementally after edits, recording which rows changed"""
        if self._pause_depth:
            self._reparse_pending = True
            return

        if self.parser is None:
            self._edit_rows = []
            return

        old_tree = self.tree
        self.tree = self._parse(self.parser, old_tree)
        if old_tree is None:
            self.changed_rows = None
        else:
            # The rows that need rehighlighting are the ones whose syntax changed
            # plus the ones that were edited, because predicates check the text
            rows = [
                (r.start_point.row, r.end_point.row)
                for r in old_tree.changed_ranges(self.tree)
            ]
            rows.extend(self._edit_rows)
            self.changed_rows = rows
        self._edit_rows = []
        self.reparsed.emit()

    def node_at_byte(self, byte_offset: int) -> Node | None:
        """Get the smallest node at a UTF-16LE byte offset"""
        if self.tree is None:
            return None
        return self.tree.root_node.descendant_for_byte_range(byte_offset, byte_offset)

    def node_at_char(self, position: int) -> Node | None:
        """Get the smallest node at a Qt position"""
        return self.node_at_byte(TrackedDocument.char_to_byte(position))

    @property
    def root_node(self) -> Node | None:
        return self.tree.root_node if self.tree is not None else None
