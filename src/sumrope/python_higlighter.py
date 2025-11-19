from typing import Optional, Any
from tree_sitter import Tree, Language, Query, QueryCursor
from Qt.QtGui import QTextCharFormat, QTextCursor, QTextDocument, QFont, QColor
import tree_sitter_python as tspython

# fmt: off
FORMAT_SPECS = {
    # Keywords and control flow
    "keyword": {"color": "#0000FF", "bold": True},
    "keyword.conditional": {"color": "#0000FF", "bold": True},
    "keyword.repeat": {"color": "#0000FF", "bold": True},
    "keyword.return": {"color": "#0000FF", "bold": True},
    "keyword.operator": {"color": "#0000FF", "bold": True},
    "keyword.import": {"color": "#0000FF", "bold": True},
    "keyword.exception": {"color": "#0000FF", "bold": True},

    # Functions and methods
    "function": {"color": "#795E26", "bold": True},
    "function.builtin": {"color": "#0000FF"},
    "function.method": {"color": "#008080"},
    "function.call": {"color": "#008080"},
    "method.call": {"color": "#008080"},

    # Types and classes
    "type": {"color": "#267F99", "bold": True},
    "type.builtin": {"color": "#0000FF"},
    "class": {"color": "#267F99", "bold": True},
    "constructor": {"color": "#267F99", "bold": True},

    # Variables and parameters
    "variable": {"color": "#001080"},
    "variable.builtin": {"color": "#0000FF"},
    "variable.parameter": {"color": "#001080"},
    "parameter": {"color": "#001080"},

    # Constants and literals
    "constant": {"color": "#0000FF"},
    "constant.builtin": {"color": "#0000FF"},
    "boolean": {"color": "#0000FF"},
    "number": {"color": "#098658"},
    "float": {"color": "#098658"},
    "string": {"color": "#A31515"},
    "string.escape": {"color": "#EE9900", "bold": True},
    "character": {"color": "#A31515"},

    # Comments and documentation
    "comment": {"color": "#008000", "italic": True},
    "comment.documentation": {"color": "#008000", "italic": True},

    # Operators and punctuation
    "operator": {"color": "#000000"},
    "punctuation": {"color": "#000000"},
    "punctuation.bracket": {"color": "#000000"},
    "punctuation.delimiter": {"color": "#000000"},

    # Decorators and attributes
    "decorator": {"color": "#808000"},
    "attribute": {"color": "#008080"},
    "property": {"color": "#008080"},

    # Special
    "tag": {"color": "#800000"},
    "label": {"color": "#000000", "bold": True},
    "namespace": {"color": "#267F99"},
    "module": {"color": "#267F99"},
}
# fmt: on


class ByteOffsetTracker:
    """Tracks byte offsets for line starts to convert between byte and character positions."""

    def __init__(self, document: QTextDocument):
        self.line_byte_offsets: list[int] = [0]  # byte offset of each line start
        self.document = document

    def byte_to_char(self, byte_offset: int) -> int:
        """Convert byte offset to character offset using line information."""
        # Find which line this byte offset is on
        line = 0
        for i, line_start in enumerate(self.line_byte_offsets):
            if byte_offset < line_start:
                line = i - 1
                break
        else:
            line = len(self.line_byte_offsets) - 1

        # Get character offset at start of line
        block = self.document.findBlockByNumber(line)
        char_offset = block.position()

        # Add the byte difference within the line
        byte_offset_in_line = byte_offset - self.line_byte_offsets[line]
        line_text = block.text()

        # Convert bytes to characters within this line
        char_offset_in_line = len(
            line_text[:byte_offset_in_line].encode("utf-8").decode("utf-8")
        )

        return char_offset + char_offset_in_line


def create_python_format_rules(
    format_specs: dict[str, dict[str, Any]],
) -> dict[str, QTextCharFormat]:
    """Create formatting rules for Python syntax highlighting.

    Format specification: each entry maps a capture name to formatting options.
    Options: color (hex), bold (bool), italic (bool)
    """
    formats = {}
    for name, spec in format_specs.items():
        fmt = QTextCharFormat()
        if "color" in spec:
            fmt.setForeground(QColor(spec["color"]))
        if spec.get("bold", False):
            fmt.setFontWeight(QFont.Bold)
        if spec.get("italic", False):
            fmt.setFontItalic(True)
        if "background" in spec:
            fmt.setBackground(QColor(spec["background"]))
        formats[name] = fmt
    return formats


class PythonSyntaxHighlighter:
    """Manages syntax highlighting for Python code using tree-sitter."""

    def __init__(
        self, language: Language, document: QTextDocument, tracker: ByteOffsetTracker
    ):
        self.language = language
        self.document = document
        self.tracker = tracker

        self.query = Query(language, tspython.HIGHLIGHTS_QUERY)
        self.query_cursor = QueryCursor(self.query)

        self.format_rules = create_python_format_rules(FORMAT_SPECS)

    def highlight_ranges(self, old_tree: Optional[Tree], new_tree: Tree) -> None:
        """Apply syntax highlighting to changed ranges in the document.

        Args:
            old_tree: Previous tree-sitter parse tree (None if first parse)
            new_tree: New tree-sitter parse tree
        """
        # Get changed ranges
        if old_tree is None:
            # First parse - highlight everything
            changed_ranges = [(0, new_tree.root_node.end_byte)]
        else:
            changed_ranges = new_tree.changed_ranges(old_tree)
            changed_ranges = [(r.start_byte, r.end_byte) for r in changed_ranges]

        # Process each changed range
        for start_byte, end_byte in changed_ranges:
            self._highlight_range(new_tree, start_byte, end_byte)

    def _highlight_range(self, tree: Tree, start_byte: int, end_byte: int) -> None:
        """Highlight a specific byte range in the document."""
        # Clear formatting in this range first
        start_char = self.tracker.byte_to_char(start_byte)
        end_char = self.tracker.byte_to_char(end_byte)

        clear_format = QTextCharFormat()
        cursor = QTextCursor(self.document)
        cursor.setPosition(start_char)
        cursor.setPosition(end_char, QTextCursor.KeepAnchor)
        cursor.setCharFormat(clear_format)

        # Execute the query using QueryCursor
        # Set the byte range for the query
        self.query_cursor.set_byte_range(start_byte, end_byte)

        # Execute the query on the tree's root node
        captures = self.query_cursor.captures(tree.root_node)

        # Apply formatting for each capture
        for capture_name, nodes in captures.items():
            # Get the format for this capture type
            format_obj = self.format_rules.get(capture_name)
            if not format_obj:
                continue
            for node in nodes:
                # Convert byte offsets to character offsets
                node_start_char = self.tracker.byte_to_char(node.start_byte)
                node_end_char = self.tracker.byte_to_char(node.end_byte)

                # Apply the format
                cursor = QTextCursor(self.document)
                cursor.setPosition(node_start_char)
                cursor.setPosition(node_end_char, QTextCursor.KeepAnchor)
                cursor.setCharFormat(format_obj)


# Usage example:
"""
# Initialize
language = Language(tspython.language())
document = QTextDocument()
tracker = ByteOffsetTracker(document)

highlighter = PythonSyntaxHighlighter(language, document, tracker)

# After parsing
highlighter.highlight_ranges(old_tree, new_tree)
"""
