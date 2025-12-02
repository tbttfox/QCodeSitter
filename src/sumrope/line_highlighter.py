from typing import Any
from Qt.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from tree_sitter import Query, QueryCursor, Tree
from .line_highlighter import TrackedDocument


class TreeSitterHighlighter(QSyntaxHighlighter):
    """
    Tree-sitter based syntax highlighter using incremental rehighlighting
    restricted to changed byte ranges.
    """

    def __init__(
        self,
        document,
        parser,
        highlights_query_source,
        format_specs,
    ):
        super().__init__(document)
        self.tree = None
        self.parser = parser
        self.query = Query(parser.language, highlights_query_source)
        self.cursor = QueryCursor(self.query)
        self.formats = self._compile_formats(format_specs)

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
    # Incremental update from new parse tree
    # ------------------------------------------------------------------

    def update_from_tree(self, new_tree: Tree):
        """
        Called after you re-parse the document.
        Rehighlight only the affected blocks.
        """
        if self.tree is None:
            # First full highlight
            self.tree = new_tree
            self.rehighlight()
            return

        changed_ranges = self.tree.changed_ranges(new_tree)
        self.tree = new_tree

        doc = self.document()
        if not isinstance(doc, TrackedDocument):
            raise ValueError("Only works with tracked document")

        for r in changed_ranges:
            start_line = r.start_point.row
            end_line = r.end_point.row
            block = doc.findBlockByNumber(start_line)

            for _ in range(start_line, end_line + 1):
                if block.isValid():
                    self.rehighlightBlock(block)
                    block = block.next()

    # ------------------------------------------------------------------
    # QSyntaxHighlighter entry point
    # ------------------------------------------------------------------

    def highlightBlock(self, text):
        if self.tree is None:
            return
        doc = self.document()
        if not isinstance(doc, TrackedDocument):
            raise ValueError("Only works with tracked document")

        block = self.currentBlock()
        block_start_char = block.position()
        block_start_byte = doc.line_to_byte(block.blockNumber())
        block_end_byte = block_start_byte + len(text.encode())

        self.cursor.set_byte_range(block_start_byte, block_end_byte)
        captures = self.cursor.captures(self.tree.root_node)
        for capture_name, nodes in captures.items():
            fmt = self.formats.get(capture_name)
            if fmt is None:
                continue
            for node in nodes:
                # Convert byte range -> character indexes
                start_char = doc.byte_to_char(node.start_byte)
                end_char = doc.byte_to_char(node.end_byte)

                # Convert to block-local indexes
                local_start = start_char - block_start_char
                local_len = max(1, end_char - start_char)

                # Apply
                if 0 <= local_start < len(text):
                    self.setFormat(local_start, local_len, fmt)
