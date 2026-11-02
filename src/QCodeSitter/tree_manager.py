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
        self._paused = False
        # Whether an edit was made while paused, so unpausing has to reparse
        self._reparse_pending = False

        # The (first, last) rows touched by edits since the last parse
        self._edit_rows: tuple[int, int] | None = None
        # The (first, last) row ranges that changed in the last parse
        # None means the whole document changed
        self.changed_rows: list[tuple[int, int]] | None = None

        self._set_parser(None)

    @property
    def language(self) -> Language | None:
        return self.parser.language if self.parser is not None else None

    @property
    def is_paused(self) -> bool:
        return self._paused

    def set_language(self, language: Language | None) -> None:
        """Change the language, and parse the document again"""
        self._set_parser(language)
        self.languageChanged.emit()
        self.parse_from_scratch()

    def _set_parser(self, language: Language | None) -> None:
        self.parser = Parser(language) if language is not None else None
        self.tree = None
        self._edit_rows = None
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
        self._edit_rows = None
        self.changed_rows = None
        self.reparsed.emit()

    def pause(self) -> None:
        """Hold reparses until `unpause`, so a group of edits is parsed once"""
        self._paused = True
        self._reparse_pending = False

    def unpause(self) -> None:
        if not self._paused:
            return
        self._paused = False
        if self._reparse_pending:
            self.reparse()

    def _track_edit_rows(
        self, start_row: int, old_end_row: int, new_end_row: int
    ) -> None:
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
        if self._paused:
            self._reparse_pending = True
            return

        if self.parser is None:
            self._edit_rows = None
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
            if self._edit_rows is not None:
                rows.append(self._edit_rows)
            self.changed_rows = rows
        self._edit_rows = None
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
        return self.tree.root_node if self.tree else None
