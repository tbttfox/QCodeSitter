from __future__ import annotations
from . import Behavior
from typing import TYPE_CHECKING, Collection
from Qt import QtGui, QtWidgets
from tree_sitter import Point

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


class HighlightMatchingBrackets(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self._ltGray = QtGui.QColor(200, 200, 200, 80)

        self.quote_chars: str = "'\""
        self.ordered_pairs: tuple[str, ...]
        self.opening_brackets: str
        self.bracket_chars: str
        self.bracket_pairs: dict[str, str]
        self.all_match_chars: str
        self.update_pairs(("()", "[]", "{}"))

        self.editor.cursorPositionChanged.connect(self.highlight_matching_brackets)
        self.updateAll()

    def update_pairs(self, ordered_pairs: Collection[str]):
        self.ordered_pairs = tuple(ordered_pairs)
        self.bracket_chars = "".join(self.ordered_pairs)
        self.opening_brackets = "".join(p[0] for p in self.ordered_pairs)
        self.bracket_pairs = {p[0]: p[1] for p in self.ordered_pairs}
        self.bracket_pairs.update({p[1]: p[0] for p in self.ordered_pairs})
        self.all_match_chars = self.quote_chars + self.bracket_chars

    def highlight_matching_brackets(self):
        """Highlight matching brackets/parens/braces using tree-sitter"""
        extra_selections = []

        if self.editor.tree_manager.tree is None:
            self.editor.selection_manager.set_selections(
                "bracket_matching", extra_selections
            )
            return

        # Find character to match
        match_info = self._find_character_to_match()
        if match_info is None:
            self.editor.selection_manager.set_selections(
                "bracket_matching", extra_selections
            )
            return

        match_char, match_pos = match_info

        # Get tree-sitter node at position
        node = self._get_node_at_position(match_pos)
        if node is None:
            self.editor.selection_manager.set_selections(
                "bracket_matching", extra_selections
            )
            return

        # Handle quotes vs brackets differently
        if match_char in self.quote_chars:
            extra_selections = self._highlight_matching_quotes(node, match_pos)
        else:
            extra_selections = self._highlight_matching_brackets_pair(node, match_char)

        self.editor.selection_manager.set_selections(
            "bracket_matching", extra_selections
        )

    def _find_character_to_match(self) -> tuple[str, int] | None:
        """Find the character near the cursor that should be matched

        Returns:
            Tuple of (character, position) or None if no matchable character found
        """
        cursor = self.editor.textCursor()
        pos = cursor.position()
        block = cursor.block()
        block_start = block.position()
        col = pos - block_start
        text = block.text()

        # Check character before cursor (preferred)
        if col > 0 and text[col - 1] in self.all_match_chars:
            return text[col - 1], pos - 1
        # Check character after cursor
        elif col < len(text) and text[col] in self.all_match_chars:
            return text[col], pos

        return None

    def _get_node_at_position(self, pos: int):
        """Get the tree-sitter node at the given character position

        Args:
            pos: Character position in the document

        Returns:
            Tree-sitter node or None
        """
        try:
            match_block = self.editor._doc.findBlock(pos)
            match_block_start = match_block.position()
            match_char_col = pos - match_block_start
            match_row = match_block.blockNumber()

            match_byte = self.editor._doc.point_to_byte(
                Point(match_row, match_char_col)
            )
            return self.editor.tree_manager.get_node_at_point(match_byte)
        except (IndexError, ValueError):
            return None

    def _highlight_matching_quotes(self, node, match_pos: int) -> list:
        """Highlight matching quotes for strings

        Args:
            node: Tree-sitter node at the quote position
            match_pos: Character position of the quote

        Returns:
            List of extra selections
        """
        extra_selections = []

        # Find the string node (parent of string_start/string_end)
        string_node = node
        while string_node:
            if string_node.type == "string":
                break
            string_node = string_node.parent

        if string_node is None:
            return extra_selections

        # Get string boundaries
        try:
            string_start_char = self.editor._doc.byte_to_char(string_node.start_byte)
            string_end_char = self.editor._doc.byte_to_char(string_node.end_byte)
        except (IndexError, ValueError):
            return extra_selections

        # Determine quote length (handle triple quotes)
        string_cursor = self.editor.textCursor()
        string_cursor.setPosition(string_start_char)
        string_cursor.setPosition(string_end_char, QtGui.QTextCursor.KeepAnchor)
        string_text = string_cursor.selectedText()

        quote_len = (
            3 if string_text.startswith('"""') or string_text.startswith("'''") else 1
        )

        # Determine which quotes to highlight
        opening_end = string_start_char + quote_len
        closing_start = string_end_char - quote_len
        cursor_at_opening = string_start_char <= match_pos < opening_end

        if cursor_at_opening:
            cursor_quote_range = (string_start_char, opening_end)
            match_quote_range = (closing_start, string_end_char)
        else:
            cursor_quote_range = (closing_start, string_end_char)
            match_quote_range = (string_start_char, opening_end)

        # Create selections
        quote_format = QtGui.QTextCharFormat()
        quote_format.setBackground(self._ltGray)

        extra_selections.append(
            self._create_selection(
                cursor_quote_range[0], cursor_quote_range[1], quote_format
            )
        )
        extra_selections.append(
            self._create_selection(
                match_quote_range[0], match_quote_range[1], quote_format
            )
        )

        return extra_selections

    def _highlight_matching_brackets_pair(self, node, match_char: str) -> list:
        """Highlight matching bracket pair

        Args:
            node: Tree-sitter node at the bracket position
            match_char: The bracket character

        Returns:
            List of extra selections
        """
        extra_selections = []

        if node.type not in self.bracket_chars:
            return extra_selections

        # Find the matching bracket node
        matching_node = self._find_matching_bracket_node(node, match_char)
        if matching_node is None:
            return extra_selections

        # Convert byte positions to character positions
        try:
            node_start_char = self.editor._doc.byte_to_char(node.start_byte)
            node_end_char = self.editor._doc.byte_to_char(node.end_byte)
            match_start_char = self.editor._doc.byte_to_char(matching_node.start_byte)
            match_end_char = self.editor._doc.byte_to_char(matching_node.end_byte)
        except (IndexError, ValueError):
            return extra_selections

        # Create selections
        bracket_format = QtGui.QTextCharFormat()
        bracket_format.setBackground(self._ltGray)

        extra_selections.append(
            self._create_selection(node_start_char, node_end_char, bracket_format)
        )
        extra_selections.append(
            self._create_selection(match_start_char, match_end_char, bracket_format)
        )

        return extra_selections

    def _find_matching_bracket_node(self, node, bracket_char: str):
        """Find the matching bracket node in the tree

        Args:
            node: The bracket node to match
            bracket_char: The bracket character

        Returns:
            Matching node or None
        """
        parent = node.parent
        if parent is None:
            return None

        matching_bracket_type = self.bracket_pairs[bracket_char]
        is_opening = bracket_char in self.opening_brackets

        # Search siblings for the matching bracket
        for sibling in parent.children:
            if sibling.type == matching_bracket_type:
                if is_opening and sibling.start_byte > node.start_byte:
                    return sibling
                elif not is_opening and sibling.start_byte < node.start_byte:
                    return sibling

        return None

    def _create_selection(self, start: int, end: int, format: QtGui.QTextCharFormat):
        """Create an ExtraSelection for the given range

        Args:
            start: Start character position
            end: End character position
            format: Text format to apply

        Returns:
            ExtraSelection object
        """
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = format
        return selection
