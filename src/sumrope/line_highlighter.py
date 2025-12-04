from typing import Any, Optional
from Qt.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from tree_sitter import Query, QueryCursor, Tree, Point
from .tree_manager import TreeManager
from .line_tracker import TrackedDocument


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

        document.byteContentsChange.connect(self._on_byte_contents_change)

        lang = self.tree_manager.parser.language
        if lang is None:
            raise RuntimeError("The tree parser must be properly set")

        # highlights_query_source = tspython.HIGHLIGHTS_QUERY,
        self.query = Query(lang, highlights_query_source)
        self.formats = self._compile_formats(format_specs)

    def setDocument(self, doc: TrackedDocument):
        self._doc = doc
        super().setDocument(doc)

    def _on_byte_contents_change(
        self,
        start_byte: int,
        old_end_byte: int,
        new_end_byte: int,
        start_point: Point,
        old_end_point: Point,
        new_end_point: Point,
    ):
        old_tree = self.tree_manager.update(
            start_byte,
            old_end_byte,
            new_end_byte,
            start_point,
            old_end_point,
            new_end_point,
        )

        if old_tree is None:
            # First full highlight
            self.rehighlight()

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

        # Calculate end byte including newline if not last line
        if block.next().isValid():
            block_end_byte = self._doc.line_to_byte(block_num + 1)
        else:
            block_end_byte = block_start_byte + len(text.encode())

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
                    # Convert byte range -> character indexes
                    start_char = self._doc.byte_to_char(node.start_byte)
                    end_char = self._doc.byte_to_char(node.end_byte)
                except (IndexError, ValueError):
                    # Byte position is beyond current document bounds
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
