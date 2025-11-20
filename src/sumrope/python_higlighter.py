import re
from typing import Optional, Any
from tree_sitter import Tree, Parser, Language, Query, QueryCursor
from Qt.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QFont,
    QColor,
)
import tree_sitter_python as tspython
from .hl_groups import FORMAT_SPECS
from stransi import Escape, SetAttribute, SetColor, Attribute, ColorRole


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


def ansi_to_rgb(code):
    for code in range(0, 16):
        if code > 8:
            level = 255
        elif code == 7:
            level = 229
        else:
            level = 205
        r = 127 if code == 8 else level if (code & 1) != 0 else 92 if code == 12 else 0
        g = 127 if code == 8 else level if (code & 2) != 0 else 92 if code == 12 else 0
        b = 127 if code == 8 else 238 if code == 4 else level if (code & 4) != 0 else 0
        print(f"{code:3d}: {r:02X} {g:02X} {b:02X}")

    for red in range(0, 6):
        for green in range(0, 6):
            for blue in range(0, 6):
                code = 16 + (red * 36) + (green * 6) + blue
                r = red   * 40 + 55 if red   != 0 else 0
                g = green * 40 + 55 if green != 0 else 0
                b = blue  * 40 + 55 if blue  != 0 else 0

    code = 232
    for gray in range(0, 24):
        level = gray * 10 + 8
        code = 232 + gray
        print(f"{code:3d}: {level:02X} {level:02X} {level:02X}")




# fmt: off
ANSI_COLORS = {
    '30': QColor("black"), '40': QColor("black"),
    '31': QColor("red"),   '41': QColor("red"),
    '32': QColor("green"), '42': QColor("green"),
    '33': QColor("yellow"),'43': QColor("yellow"),
    '34': QColor("blue"),  '44': QColor("blue"),
    '35': QColor("magenta"), '45': QColor("magenta"),
    '36': QColor("cyan"),  '46': QColor("cyan"),
    '37': QColor("white"), '47': QColor("white"),
}
# fmt: on



class SingleLineHighlighter(QSyntaxHighlighter):
    """A qsyntaxhighlighter that formats a single line"""

    # Regex to match common ANSI escape sequences
    ansi_splitter = re.compile(r'(\x1b\[[0-9;]*m)')
    byte_splitter = re.compile(
        r'[\x00-\x7f]+|[\x80-\u07ff]+|[\u0800-\uffff]+|[\U00010000-\U0010ffff]+'
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.format_rules = load_python_format_rules(FORMAT_SPECS)
        self.language = Language(tspython.language())
        self.parser = Parser(self.language)
        self.query = Query(self.language, tspython.HIGHLIGHTS_QUERY)
        self.query_cursor = QueryCursor(self.query)

    def build_charmap(self, text):
        """Build a mapping from byte index to character index as a list"""
        charmap = []
        charidx = 0
        for seg in self.byte_splitter.findall(text):
            bytesize = len(seg[0].encode('utf8'))
            charcount = len(seg)
            for _ in range(charcount):
                charmap.extend([charidx] * bytesize)
                charidx += 1
        return charmap

    def extract_ansi(self, text: str) -> tuple[str, list[tuple[str, int, int]]]:
        """Extract the ansi codes from some text, keeping track of their character offsets"""
        sp = self.ansi_splitter.split(text)
        curidx = 0
        codes = []
        chunks = []
        curcode = ("\033[0m", 0)
        for i, seg in enumerate(sp):
            if i % 2:  # Ansi code
                curcode = (seg, curidx)
            else:  # regular text
                chunks.append(text)
                curidx += len(text)
                codes.append((curcode[0], curcode[1], curidx))
        return ''.join(chunks), codes

    def highlightBlock(self, text: str):
        """Apply highlighting to a single block (line)"""
        text, ansi = self.extract_ansi(text)
        bstr = text.encode('utf8')
        tree = self.parser.parse(bstr)
        self.query_cursor.set_byte_range(0, tree.root_node.end_byte)
        captures = self.query_cursor.captures(tree.root_node)
        charmap = self.build_charmap(text)

        # Apply formatting for each capture
        for capture_name, nodes in captures.items():
            # Get the format for this capture type
            format_obj = self.format_rules.get(capture_name)
            if not format_obj:
                continue
            for node in nodes:
                # Convert byte offsets to character offsets
                startchar = charmap[node.start_byte]
                endchar = charmap[node.end_byte]
                self.setFormat(startchar, endchar - startchar, format_obj)

        current_format = QTextCharFormat()
        for codes, start, end in ansi:
            for s in Escape(codes).instructions():
                if isinstance(s, SetAttribute):
                    if s.attribute == Attribute.NORMAL:
                        current_format = QTextCharFormat()
                    elif s.attribute == Attribute.BOLD:
                        current_format.setFontWeight(QFont.Weight.Bold)
                    elif s.attribute == Attribute.DIM:
                        current_format.setFontWeight(QFont.Weight.Light)
                    elif s.attribute == Attribute.NEITHER_BOLD_NOR_DIM:
                        current_format.setFontWeight(QFont.Weight.Normal)
                    elif s.attribute == Attribute.ITALIC:
                        current_format.setFontItalic(True)
                    elif s.attribute == Attribute.NOT_ITALIC:
                        current_format.setFontItalic(False)
                    elif s.attribute == Attribute.UNDERLINE:
                        current_format.setFontUnderline(True)
                    elif s.attribute == Attribute.NOT_UNDERLINE:
                        current_format.setFontUnderline(False)
                elif isinstance(s, SetColor):
                    if s.color is not None:
                        ocolor = s.color.rgb
                        color = QColor.fromRgbF(ocolor.red, ocolor.green, ocolor.blue)
                        if s.role == ColorRole.Foreground:
                            current_format.setForeground(color)
                        elif s.role == ColorRole.Background:
                            current_format.setBackground(color)
            self.setFormat(start, end - start, current_format)


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

        self.format_rules = load_python_format_rules(FORMAT_SPECS)

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
