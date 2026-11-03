from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from Qt import QtGui, QtWidgets

from ..gui_colors import GuiColors, gui_color
from ..languages import language_spec
from ..tracked_document import len16, utf16_to_index
from ..utils import MM
from . import Behavior

if TYPE_CHECKING:
    from tree_sitter import Node

    from ..code_editor import CodeEditor


class HighlightMatchingBrackets(Behavior):
    """Highlight a bracket or quote next to the cursor, and the one it pairs with

    The pairs come from the tree-sitter tree, so brackets in strings and
    comments don't match the code around them. The brackets and quotes come
    from the "highlight_bracket_pairs" and "highlight_quote_chars" options
    """

    SOURCE = "bracket_matching"

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.watch_options(
            {
                "colors": self._set_colors,
                "highlight_bracket_pairs": self._set_bracket_pairs,
            }
        )
        self.connect(
            self.editor.cursorPositionChanged, self.highlight_matching_brackets
        )

    def _set_colors(self, colors: GuiColors) -> None:
        self._format = QtGui.QTextCharFormat()
        self._format.setBackground(gui_color(colors, "pair_hl"))

    def _set_bracket_pairs(self, ordered_pairs: Collection[str]) -> None:
        """Set the brackets from strings of an opening and closing character, ie "()" """
        self.opening_brackets = "".join(p[0] for p in ordered_pairs)
        self.bracket_chars = "".join(ordered_pairs)
        self.bracket_pairs = {p[0]: p[1] for p in ordered_pairs}
        self.bracket_pairs.update({p[1]: p[0] for p in ordered_pairs})

    @property
    def _quote_chars(self) -> str:
        return self.options["highlight_quote_chars"]

    def on_remove(self) -> None:
        self.editor.clear_selections(self.SOURCE)

    def highlight_matching_brackets(self) -> None:
        self.editor.set_selections(self.SOURCE, self._matching_selections())

    def _matching_selections(self) -> list[QtWidgets.QTextEdit.ExtraSelection]:
        match_info = self._find_character_to_match()
        if match_info is None:
            return []
        match_char, match_pos = match_info
        node = self.editor.tree_manager.node_at_char(match_pos)
        if node is None:
            return []

        if match_char in self._quote_chars:
            ranges = self._matching_quote_ranges(node, match_pos)
        else:
            ranges = self._matching_bracket_ranges(node, match_char)
        return [self._create_selection(start, end) for start, end in ranges]

    def _find_character_to_match(self) -> tuple[str, int] | None:
        """Find the bracket or quote next to the cursor, preferring the one before it

        Returns:
            The character and its position, or None if neither side matches
        """
        cursor = self.editor.textCursor()
        pos = cursor.position()
        text = cursor.block().text()
        index = utf16_to_index(text, cursor.positionInBlock())
        matchable = self._quote_chars + self.bracket_chars
        if index > 0 and text[index - 1] in matchable:
            char = text[index - 1]
            return char, pos - len16(char)
        if index < len(text) and text[index] in matchable:
            return text[index], pos
        return None

    def _matching_quote_ranges(
        self, node: Node, match_pos: int
    ) -> list[tuple[int, int]]:
        """Get the ranges of the quote at match_pos, and the other end of its string"""
        spec = language_spec(self.editor.tree_manager.language)
        string_node: Node | None = node
        while string_node is not None and string_node.type != spec.string_type:
            string_node = string_node.parent
        if string_node is None:
            return []

        # The delimiter nodes include triple quotes and prefixes like f"
        delimiters = {child.type: child for child in string_node.children}
        start_type, end_type = spec.string_delimiter_types
        start_node = delimiters.get(start_type)
        end_node = delimiters.get(end_type)
        if start_node is None or end_node is None:
            return []

        doc = self.editor.document()
        opening, closing = (
            (doc.byte_to_char(n.start_byte), doc.byte_to_char(n.end_byte))
            for n in (start_node, end_node)
        )
        if opening[0] <= match_pos < opening[1]:
            return [opening, closing]
        if closing[0] <= match_pos < closing[1]:
            return [closing, opening]
        # A quote inside the string, like the apostrophe in "don't"
        return []

    def _matching_bracket_ranges(
        self, node: Node, match_char: str
    ) -> list[tuple[int, int]]:
        """Get the ranges of a bracket node, and its sibling it pairs with

        The partner is the nearest balanced one, which matters in error nodes
        that hold several unmatched brackets
        """
        if node.type not in self.bracket_pairs or node.parent is None:
            return []

        partner_type = self.bracket_pairs[match_char]
        siblings = node.parent.children
        index = siblings.index(node)
        # Opening brackets match forwards, and closing brackets match backwards
        if match_char in self.opening_brackets:
            candidates = siblings[index + 1 :]
        else:
            candidates = siblings[index - 1 :: -1] if index else []
        partner = None
        depth = 0
        for sibling in candidates:
            if sibling.type == node.type:
                depth += 1
            elif sibling.type == partner_type:
                if depth == 0:
                    partner = sibling
                    break
                depth -= 1
        if partner is None:
            return []

        doc = self.editor.document()
        return [
            (doc.byte_to_char(n.start_byte), doc.byte_to_char(n.end_byte))
            for n in (node, partner)
        ]

    def _create_selection(
        self, start: int, end: int
    ) -> QtWidgets.QTextEdit.ExtraSelection:
        """Create an ExtraSelection for a range of the document

        The range is clamped to the document, which it can pass
        if the tree hasn't caught up with an edit yet
        """
        # -1 for the paragraph separator at the end of the document
        doc_length = self.editor.document().characterCount() - 1
        cursor = self.editor.textCursor()
        cursor.setPosition(min(start, doc_length))
        cursor.setPosition(min(end, doc_length), MM.KeepAnchor)
        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = self._format
        return selection
