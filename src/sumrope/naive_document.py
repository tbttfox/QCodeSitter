from typing import Any
import difflib

from Qt.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Query, QueryCursor, Point, Tree

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
        self.prev = ""
        self.old_char_to_line = {0: 0}
        self.old_line_to_char = {0: 0}
        self.tree: Tree = self.parser.parse(b'')

    def _changed(self, _start, _rem, _add):
        print("-----------------------------------------")
        txt = self.toPlainText()
        bbb = txt.encode("utf8")

        byte_to_char = {}
        char_to_bytes = {}
        char_to_line = {}
        line_to_char = {}
        block = self.begin()
        curbyte = 0
        while block.isValid():
            pos = block.position()
            line_to_char[block.blockNumber()] = pos
            for t in block.text() + "\n":
                char_to_line[pos] = block.blockNumber()
                for _ in range(len(t.encode("utf8"))):
                    byte_to_char[curbyte] = pos
                    char_to_bytes.setdefault(pos, []).append(curbyte)
                    curbyte += 1
                pos += 1
            block = block.next()
        char_to_byte = {k: min(v) for k, v in char_to_bytes.items()}

        matcher = difflib.SequenceMatcher(None, self.prev, txt)
        crr = [oc for oc in matcher.get_opcodes() if oc[0] != "equal"]
        if not crr:
            return
        assert len(crr) == 1
        crr = crr[0]

        start_byte = char_to_byte[crr[1]]
        start_line = char_to_line[crr[1]]

        new_end_byte = char_to_byte[crr[4]]
        start_col = start_byte - line_to_char[start_line]
        new_end_line = char_to_line[crr[4]]
        new_end_col = new_end_byte - line_to_char[new_end_line]

        old_end_byte = char_to_byte[crr[2]]
        start_col = start_byte - self.old_line_to_char[start_line]
        old_end_line = self.old_char_to_line[crr[2]]
        old_end_col = old_end_byte - self.old_line_to_char[old_end_line]

        self.old_char_to_line = char_to_line
        self.old_line_to_char = line_to_char
        self.prev = txt

        # fmt: off
        print(
            "self.tree.edit:",
            "\nstart_byte", start_byte,
            "\nold_end_byte", old_end_byte,
            "\nnew_end_byte", new_end_byte,
            "\nstart_point", Point(start_line, start_col),
            "\nold_end_point", Point(old_end_line, old_end_col),
            "\nnew_end_point", Point(new_end_line, new_end_col),
        )
        # fmt: on

        self.tree.edit(
            start_byte=start_byte,
            old_end_byte=old_end_byte,
            new_end_byte=new_end_byte,
            start_point=Point(start_line, start_col),
            old_end_point=Point(old_end_line, old_end_col),
            new_end_point=Point(new_end_line, new_end_col),
        )
        old_tree = self.tree
        self.tree = self.parser.parse(bbb, old_tree)
        changed_ranges = old_tree.changed_ranges(self.tree)
        self.highlight_captures(changed_ranges, byte_to_char)

    def highlight_captures(self, changed_ranges, byte_to_char):
        # Clear previous formatting
        clear_format = QTextCharFormat()
        cursor = QTextCursor(self)
        print("CHANGED", changed_ranges)
        for rng in changed_ranges:

            cursor.setPosition(byte_to_char[rng.start_byte])
            cursor.setPosition(byte_to_char[rng.end_byte], QTextCursor.KeepAnchor)
            cursor.setCharFormat(clear_format)

            self.query_cursor.set_byte_range(rng.start_byte, rng.end_byte)
            captures = self.query_cursor.captures(self.tree.root_node)

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
