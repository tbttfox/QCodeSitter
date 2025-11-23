from typing import Any

from Qt.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Query, QueryCursor

from .hl_groups import FORMAT_SPECS

PY_LANGUAGE = Language(tspython.language())


def load_python_format_rules(
    format_specs: dict[str, dict[str, Any]],
) -> dict[str, QTextCharFormat]:
    """Load formatting rules for Python syntax highlighting.

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


class NaiveDocument(QTextDocument):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parser = Parser(PY_LANGUAGE)
        self.query = Query(PY_LANGUAGE, tspython.HIGHLIGHTS_QUERY)
        self.query_cursor = QueryCursor(self.query)
        self.format_rules = load_python_format_rules(FORMAT_SPECS)
        self.contentsChange.connect(self._changed)

    def _changed(self, _start, _rem, _add):
        txt = self.toPlainText()
        bbb = txt.encode("utf8")

        byte_to_char = {}
        block = self.begin()
        curbyte = 0
        while block.isValid():
            pos = block.position()
            for t in block.text() + "\n":
                for _ in range(len(t.encode("utf8"))):
                    byte_to_char[curbyte] = pos
                    curbyte += 1
                pos += 1
            block = block.next()

        tree = self.parser.parse(bbb)

        # Clear previous formatting
        clear_format = QTextCharFormat()
        cursor = QTextCursor(self)
        cursor.setPosition(0)
        cursor.setPosition(self.characterCount() - 1, QTextCursor.KeepAnchor)
        cursor.setCharFormat(clear_format)

        # Execute the query using QueryCursor
        self.query_cursor.set_byte_range(0, len(bbb))
        captures = self.query_cursor.captures(tree.root_node)

        for capture_name, nodes in captures.items():
            format_obj = self.format_rules.get(capture_name)
            if not format_obj:
                continue
            for node in nodes:
                # Convert byte offsets to character offsets
                node_start_char = byte_to_char[node.start_byte]
                node_end_char = byte_to_char[node.end_byte]

                # Apply the format
                cursor.setPosition(node_start_char)
                cursor.setPosition(node_end_char, QTextCursor.KeepAnchor)
                cursor.setCharFormat(format_obj)
