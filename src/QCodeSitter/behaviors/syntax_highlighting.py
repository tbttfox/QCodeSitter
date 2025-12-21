from __future__ import annotations

from . import Behavior
from typing import TYPE_CHECKING, Optional, Any
from Qt.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from tree_sitter import Query, QueryCursor

if TYPE_CHECKING:
    from .tree_manager import TreeManager
    from .line_tracker import TrackedDocument
    from ..line_editor import CodeEditor


class TreeSitterHighlighter(QSyntaxHighlighter):
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

        lang = self.tree_manager.parser.language
        if lang is None:
            raise RuntimeError("The tree parser must be properly set")

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
    ) -> dict[str, QTextCharFormat]:
        """Convert user style specs -> QTextCharFormat instances."""
        out = {}

        for name, spec in format_specs.items():
            fmt = QTextCharFormat()
            if "color" in spec:
                fmt.setForeground(QColor(spec["color"]))
            if spec.get("bold"):
                fmt.setFontWeight(QFont.Bold)
            if spec.get("italic"):
                fmt.setFontItalic(True)
            out[name] = fmt

        return out

    # ------------------------------------------------------------------
    # QSyntaxHighlighter entry point
    # ------------------------------------------------------------------

    def highlightBlock(self, text: str):
        if self.tree_manager.tree is None:
            return

        block = self.currentBlock()
        if not block.isValid():
            return

        block_num = block.blockNumber()
        block_start_char = block.position()
        block_start_byte = self._doc.line_to_byte(block_num)

        # Calculate end UTF-16 offset including newline if not last line
        if block.next().isValid():
            block_end_byte = self._doc.line_to_byte(block_num + 1)
        else:
            # In UTF-16, len(text) gives us the code unit count directly
            block_end_byte = block_start_byte + len(text) * 2

        # Skip highlighting for empty blocks (can happen during undo to empty document)
        if block_start_byte >= block_end_byte:
            return

        # Create a fresh QueryCursor for each block to avoid stale state issues
        cursor = QueryCursor(self.query)
        cursor.set_byte_range(block_start_byte, block_end_byte)
        captures = cursor.captures(self.tree_manager.tree.root_node)
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


class DummyHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, block):
        return


class SyntaxHighlighting(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"highlights"})
        self._highlights = None
        self.highlighter: Optional[TreeSitterHighlighter] = None
        self.updateAll()

    @property
    def highlights(self):
        return self._highlights

    @highlights.setter
    def highlights(self, value):
        if not value:
            self.highlighter = None
            return
        hlquery, fmts = value
        self.highlighter = TreeSitterHighlighter(
            self.editor._doc, self.editor.tree_manager, hlquery, fmts
        )

    def remove(self):
        self.highlighter = None

        mydoc = self.editor.document()
        newHigh = DummyHighlighter(mydoc)
        newHigh.rehighlight()
