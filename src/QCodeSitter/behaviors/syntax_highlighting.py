from __future__ import annotations

from . import Behavior, HasUndoRedo
from typing import TYPE_CHECKING, Optional, Any
from Qt import QtGui
from tree_sitter import Query, QueryCursor

if TYPE_CHECKING:
    from ..tree_manager import TreeManager
    from ..line_tracker import TrackedDocument
    from ..code_editor import CodeEditor


class TreeSitterHighlighter(QtGui.QSyntaxHighlighter):
    """
    Tree-sitter based syntax highlighter using incremental rehighlighting
    restricted to changed byte ranges.
    """

    def __init__(
        self,
        document: TrackedDocument,
        tree_manager: TreeManager,
        highlights_query_source: str,
        format_specs: dict[str, dict[str, Any]],
    ):
        super().__init__(document)
        self.tree_manager = tree_manager
        self._doc: TrackedDocument = document
        self._enabled = True  # Flag to temporarily disable highlighting

        parser = self.tree_manager.parser
        if parser is None:
            raise RuntimeError("The tree parser must be properly set")
        lang = parser.language
        if lang is None:
            raise RuntimeError("The tree language must be properly set")

        # highlights_query_source = tspython.HIGHLIGHTS_QUERY,
        self.query = Query(lang, highlights_query_source)
        self.formats = self._compile_formats(format_specs)

    def setDocument(self, doc: TrackedDocument):
        self._doc = doc
        super().setDocument(doc)

    # ------------------------------------------------------------------
    # Text formats
    # ------------------------------------------------------------------

    def _compile_formats(
        self, format_specs: dict[str, dict[str, Any]]
    ) -> dict[str, QtGui.QTextCharFormat]:
        """Convert user style specs -> QtGui.QTextCharFormat instances."""
        out = {}

        for name, spec in format_specs.items():
            fmt = QtGui.QTextCharFormat()
            if "color" in spec:
                fmt.setForeground(QtGui.QColor(spec["color"]))
            if spec.get("bold"):
                fmt.setFontWeight(QtGui.QFont.Weight.Bold)
            if spec.get("italic"):
                fmt.setFontItalic(True)
            out[name] = fmt

        return out

    # ------------------------------------------------------------------
    # QtGui.QSyntaxHighlighter entry point
    # ------------------------------------------------------------------
    def highlightBlock(self, text: str):
        # Quick exit if highlighting is disabled
        if not self._enabled:
            return

        if self.tree_manager.tree is None:
            return

        block = self.currentBlock()
        if not block.isValid():
            return

        block_num = block.blockNumber()

        # Get document bounds safely
        try:
            block_start_char = block.position()
            block_start_byte = self._doc.line_to_byte(block_num)

            # Calculate end UTF-16 offset including newline if not last line
            if block.next().isValid():
                block_end_byte = self._doc.line_to_byte(block_num + 1)
            else:
                # In UTF-16, len(text) gives us the code unit count directly
                block_end_byte = block_start_byte + len(text) * 2
        except (IndexError, RuntimeError):
            # Block number is out of range - document changed during highlighting
            return

        # Skip highlighting for empty blocks (can happen during undo to empty document)
        if block_start_byte >= block_end_byte:
            return

        # Validate that tree is still valid for this document state
        # If the tree's byte range doesn't cover our block, skip highlighting
        root = self.tree_manager.tree.root_node
        if root is None or block_end_byte > root.end_byte:
            # Tree is stale, skip highlighting until tree updates
            return

        # Create a fresh QueryCursor for each block to avoid stale state issues
        try:
            cursor = QueryCursor(self.query)
            cursor.set_byte_range(block_start_byte, block_end_byte)
            captures = cursor.captures(root)
        except (ValueError, RuntimeError):
            # Query failed - tree might be in inconsistent state
            return
        for capture_name, nodes in captures.items():
            fmt = self.formats.get(capture_name)
            if fmt is None:
                continue
            for node in nodes:
                # Skip nodes that are beyond the current document
                # (can happen during undo when tree has stale nodes)
                if node.start_byte > block_end_byte:
                    continue

                try:
                    # With UTF-16, byte offsets ARE character indexes
                    start_char = self._doc.byte_to_char(node.start_byte)
                    end_char = self._doc.byte_to_char(node.end_byte)
                except (IndexError, ValueError) as e:
                    # Position is beyond current document bounds
                    continue

                # Convert to block-local and clamp to boundaries
                local_start = start_char - block_start_char
                local_end = end_char - block_start_char

                # Clamp to [0, len(text)]
                local_start = max(0, local_start)
                local_end = min(len(text), local_end)
                local_len = local_end - local_start

                # Apply format if valid range
                if local_len > 0:
                    self.setFormat(local_start, local_len, fmt)


class DummyHighlighter(QtGui.QSyntaxHighlighter):
    def highlightBlock(self, text):
        return


class SyntaxHighlighting(Behavior, HasUndoRedo):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"highlights"})
        self._highlights = None
        self.highlighter: Optional[TreeSitterHighlighter] = None
        self.updateAll()

    def prepareUndo(self):
        """Disable highlighting before undo to prevent stale tree issues"""
        if self.highlighter:
            self.highlighter._enabled = False

    def prepareRedo(self):
        """Disable highlighting before redo to prevent stale tree issues"""
        if self.highlighter:
            self.highlighter._enabled = False

    def afterUndoRedo(self):
        """Update tree and rehighlight after undo/redo completes"""
        if self.highlighter:
            # Update the tree first
            self.editor.tree_manager.fullUpdate()
            # Re-enable highlighting and rehighlight
            self.highlighter._enabled = True
            self.highlighter.rehighlight()

    @property
    def highlights(self):
        return self._highlights

    @highlights.setter
    def highlights(self, value):
        if not value:
            self.highlighter = None
            return

        if self.editor.tree_manager.parser is None:
            self.highlighter = None
            return

        if self.editor.tree_manager.parser.language is None:
            self.highlighter = None
            return

        hlquery, fmts = value
        self.highlighter = TreeSitterHighlighter(
            self.editor._doc, self.editor.tree_manager, hlquery, fmts
        )
        self.editor.tree_manager.reparsed.connect(self._on_reparsed)

    def _on_reparsed(self):
        if self.highlighter:
            self.highlighter.rehighlight()

    def remove(self):
        self.highlighter = None

        mydoc = self.editor.document()
        newHigh = DummyHighlighter(mydoc)
        newHigh.rehighlight()
