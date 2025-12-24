from __future__ import annotations
from tree_sitter import Language, Parser, Tree, Point, Node
from typing import Optional, TYPE_CHECKING
from .constants import ENC

if TYPE_CHECKING:
    from Qt.QtWidgets import QPlainTextEdit
    from Qt.QtGui import QTextBlock


class TreeManager:
    """Manages the tree-sitter parse tree with incremental updates

    This class owns the parse tree and provides a shared resource for both
    syntax highlighting and syntax analysis. It supports incremental updates
    to efficiently re-parse only the changed portions of the document.
    """

    def __init__(
        self,
        editor: QPlainTextEdit,
        language: Language,
    ):
        """Initialize the tree manager

        Args:
            language: The tree-sitter Language to use for parsing
            source_callback: Callback function to provide source bytes to the parser.
                Signature: (byte_offset: int, point: Point) -> bytes
                Note: bytes should be UTF-16LE encoded
        """
        self.editor = editor
        self.parser = Parser(language)
        self.tree: Optional[Tree] = None
        self._source_callback = self.treesitter_source_callback

    def treesitter_source_callback(self, _byte_offset: int, ts_point: Point) -> bytes:
        """Provide source bytes to tree-sitter parser

        A callback for efficient access to the underlying UTF-16LE encoded data

        Args:
            byte_offset: The byte offset in UTF-16LE encoding where data is requested
            ts_point: The (row, column) point in code units where data is requested

        Returns:
            UTF-16LE encoded bytes from the requested position to end of document
        """
        # Clear cache at the start of each parse (when row 0 is requested)
        # This ensures we don't use stale block references after document edits
        if ts_point.row == 0:
            self._ts_prediction = {}

        curblock: Optional[QTextBlock] = self._ts_prediction.get(ts_point.row)
        if curblock is None:
            try:
                curblock = self.editor.document().findBlockByNumber(ts_point.row)
            except IndexError:
                self._ts_prediction = {}
                return b""

        # Check if block is valid (can be invalid after undo)
        if not curblock.isValid():
            self._ts_prediction = {}
            return b""

        self._ts_prediction[ts_point.row] = curblock
        nxt = curblock.next()
        self._ts_prediction[ts_point.row + 1] = nxt
        suffix = "\n" if nxt.isValid() else ""
        linetext = curblock.text() + suffix

        # Return UTF-16LE encoded bytes starting from the column offset
        # When using encoding='utf16', ts_point.column is in BYTES, not code units
        # So we need to divide by 2 to get the character position
        return linetext.encode(ENC)[ts_point.column :]

    def fullUpdate(self):
        self.tree = self.parser.parse(self._source_callback, encoding="utf16")

    def update(
        self,
        start_byte: int,
        old_end_byte: int,
        new_end_byte: int,
        start_point: Point,
        old_end_point: Point,
        new_end_point: Point,
    ) -> Optional[Tree]:
        """Incrementally update the parse tree after document changes

        Args:
            start_byte: UTF-16 code unit offset where the change started
            old_end_byte: UTF-16 code unit offset where the change ended (before change)
            new_end_byte: UTF-16 code unit offset where the change ends (after change)
            start_point: (row, column) where the change started (column in UTF-16 code units)
            old_end_point: (row, column) where the change ended (before change)
            new_end_point: (row, column) where the change ends (after change)
        """
        old_tree = self.tree
        if self.tree is not None:
            self.tree.edit(
                start_byte=start_byte,
                old_end_byte=old_end_byte,
                new_end_byte=new_end_byte,
                start_point=start_point,
                old_end_point=old_end_point,
                new_end_point=new_end_point,
            )
            self.tree = self.parser.parse(
                self._source_callback, self.tree, encoding="utf16"
            )
        else:
            # First parse - no old tree to pass
            self.tree = self.parser.parse(self._source_callback, encoding="utf16")
        return old_tree

    def get_node_at_point(self, byte_offset: int) -> Optional[Node]:
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
    def root_node(self) -> Optional[Node]:
        """Get the root node of the parse tree

        Returns:
            The root Node of the tree, or None if no tree exists
        """
        return self.tree.root_node if self.tree else None
