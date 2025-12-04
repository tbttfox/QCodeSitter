from __future__ import annotations
from . import Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtWidgets
from tree_sitter import Point

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


class HighlightMatchingBrackets(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor, set())
        self.editor.cursorPositionChanged.connect(self.highlight_matching_brackets)

    def highlight_matching_brackets(self):
        """Highlight matching brackets/parens/braces using tree-sitter"""
        extra_selections = []

        # First add occurrence highlights if any text is selected
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        if selected_text and len(selected_text) >= 2 and len(selected_text) <= 100:
            format = QtGui.QTextCharFormat()
            format.setBackground(QtGui.QColor(255, 255, 0, 80))

            doc = self.editor.document()
            search_cursor = QtGui.QTextCursor(doc)

            while True:
                search_cursor = doc.find(selected_text, search_cursor)
                if search_cursor.isNull():
                    break

                if (
                    search_cursor.position() != cursor.position()
                    or search_cursor.anchor() != cursor.anchor()
                ):
                    selection = QtWidgets.QTextEdit.ExtraSelection()
                    selection.cursor = search_cursor
                    selection.format = format
                    extra_selections.append(selection)

        # Now check for bracket matching
        if self.editor.tree_manager.tree is None:
            self.editor.setExtraSelections(extra_selections)
            return

        cursor = self.editor.textCursor()
        pos = cursor.position()
        block = cursor.block()
        block_start = block.position()
        col = pos - block_start

        # Check character before and after cursor
        text = block.text()
        bracket_chars = "()[]{}"
        quote_chars = "'\""
        all_match_chars = bracket_chars + quote_chars
        opening_brackets = "([{"
        bracket_pairs = {"(": ")", "[": "]", "{": "}", ")": "(", "]": "[", "}": "{"}

        match_char = None
        match_pos = None

        # Check character before cursor (preferred)
        if col > 0 and text[col - 1] in all_match_chars:
            match_char = text[col - 1]
            match_pos = pos - 1
        # Check character after cursor
        elif col < len(text) and text[col] in all_match_chars:
            match_char = text[col]
            match_pos = pos

        if match_char is None or match_pos is None:
            self.editor.setExtraSelections(extra_selections)
            return

        # Convert character position to byte offset
        # Find which block contains this character position
        try:
            match_block = self.editor._doc.findBlock(match_pos)
            match_block_start = match_block.position()
            match_char_col = match_pos - match_block_start
            match_row = match_block.blockNumber()

            # Convert character column to byte column
            match_text = match_block.text()
            match_byte_col = len(match_text[:match_char_col].encode("utf-8"))

            # Convert row/col to byte offset using point_to_byte
            match_byte = self.editor._doc.point_to_byte(
                Point(match_row, match_byte_col)
            )
        except (IndexError, ValueError):
            self.editor.setExtraSelections(extra_selections)
            return

        # Get the node at the match position
        node = self.editor.tree_manager.get_node_at_point(match_byte)
        if node is None:
            self.editor.setExtraSelections(extra_selections)
            return

        # Handle quotes differently from brackets
        if match_char in quote_chars:
            # For quotes, we need to find the full string node (not just string_start/string_end)
            # Walk up to find a string node, but if we find string_start or string_end, keep going up
            string_node = node
            while string_node:
                # We want the parent 'string' node, not the child 'string_start'/'string_end' nodes
                if string_node.type == "string":
                    break
                string_node = string_node.parent

            if string_node is None:
                self.editor.setExtraSelections(extra_selections)
                return

            # For strings, highlight the opening and closing quotes
            # Get the string content from the document
            try:
                string_start_char = self.editor._doc.byte_to_char(
                    string_node.start_byte
                )
                string_end_char = self.editor._doc.byte_to_char(string_node.end_byte)
            except (IndexError, ValueError):
                self.editor.setExtraSelections(extra_selections)
                return

            # Get the actual string text to determine quote length (handle triple quotes)
            string_cursor = self.editor.textCursor()
            string_cursor.setPosition(string_start_char)
            string_cursor.setPosition(string_end_char, QtGui.QTextCursor.KeepAnchor)
            string_text = string_cursor.selectedText()

            # Detect quote type (single/double/triple)
            quote_len = (
                3
                if string_text.startswith('"""') or string_text.startswith("'''")
                else 1
            )

            # Determine if cursor is at opening or closing quote
            # match_pos is the position of the quote character itself
            opening_end = string_start_char + quote_len
            closing_start = string_end_char - quote_len

            # Check if the quote at match_pos is within the opening quotes range
            cursor_at_opening = string_start_char <= match_pos < opening_end
            # Check if the quote at match_pos is within the closing quotes range
            cursor_at_closing = closing_start <= match_pos < string_end_char

            # Create highlight format
            quote_format = QtGui.QTextCharFormat()
            quote_format.setBackground(QtGui.QColor(200, 200, 200))  # Light gray

            # Determine which quotes to highlight based on cursor position
            # If cursor is at opening quote, highlight opening and closing
            # If cursor is at closing quote, highlight closing and opening
            # If cursor is somehow not at either (shouldn't happen), highlight both
            if cursor_at_opening or not cursor_at_closing:
                # Cursor is at opening quote (or default case)
                cursor_quote_start = string_start_char
                cursor_quote_end = opening_end
                match_quote_start = closing_start
                match_quote_end = string_end_char
            else:
                # Cursor is at closing quote
                cursor_quote_start = closing_start
                cursor_quote_end = string_end_char
                match_quote_start = string_start_char
                match_quote_end = opening_end

            # Highlight quote at cursor
            cursor1 = self.editor.textCursor()
            cursor1.setPosition(cursor_quote_start)
            cursor1.setPosition(cursor_quote_end, QtGui.QTextCursor.KeepAnchor)
            selection1 = QtWidgets.QTextEdit.ExtraSelection()
            selection1.cursor = cursor1
            selection1.format = quote_format
            extra_selections.append(selection1)

            # Highlight matching quote
            cursor2 = self.editor.textCursor()
            cursor2.setPosition(match_quote_start)
            cursor2.setPosition(match_quote_end, QtGui.QTextCursor.KeepAnchor)
            selection2 = QtWidgets.QTextEdit.ExtraSelection()
            selection2.cursor = cursor2
            selection2.format = quote_format
            extra_selections.append(selection2)

            self.editor.setExtraSelections(extra_selections)
            return

        # Handle brackets
        if node.type not in bracket_chars:
            self.editor.setExtraSelections(extra_selections)
            return

        # Find the matching bracket
        # For tree-sitter, matching brackets are siblings with the same parent
        matching_node = None
        parent = node.parent

        if parent is not None:
            matching_bracket_type = bracket_pairs[match_char]

            # Search siblings for the matching bracket
            for sibling in parent.children:
                if sibling.type == matching_bracket_type:
                    # Found a potential match
                    # For opening brackets, find the matching closing bracket (comes after)
                    if match_char in opening_brackets:
                        if sibling.start_byte > node.start_byte:
                            matching_node = sibling
                            break
                    # For closing brackets, find the matching opening bracket (comes before)
                    else:
                        if sibling.start_byte < node.start_byte:
                            matching_node = sibling

        if matching_node is None:
            self.editor.setExtraSelections(extra_selections)
            return

        # Convert byte positions to character positions
        try:
            node_start_char = self.editor._doc.byte_to_char(node.start_byte)
            node_end_char = self.editor._doc.byte_to_char(node.end_byte)
            match_start_char = self.editor._doc.byte_to_char(matching_node.start_byte)
            match_end_char = self.editor._doc.byte_to_char(matching_node.end_byte)
        except (IndexError, ValueError):
            self.editor.setExtraSelections(extra_selections)
            return

        # Create highlight format
        bracket_format = QtGui.QTextCharFormat()
        bracket_format.setBackground(QtGui.QColor(200, 200, 200))  # Light gray

        # Highlight the bracket under/near cursor
        cursor1 = self.editor.textCursor()
        cursor1.setPosition(node_start_char)
        cursor1.setPosition(node_end_char, QtGui.QTextCursor.KeepAnchor)
        selection1 = QtWidgets.QTextEdit.ExtraSelection()
        selection1.cursor = cursor1
        selection1.format = bracket_format
        extra_selections.append(selection1)

        # Highlight the matching bracket
        cursor2 = self.editor.textCursor()
        cursor2.setPosition(match_start_char)
        cursor2.setPosition(match_end_char, QtGui.QTextCursor.KeepAnchor)
        selection2 = QtWidgets.QTextEdit.ExtraSelection()
        selection2.cursor = cursor2
        selection2.format = bracket_format
        extra_selections.append(selection2)

        self.editor.setExtraSelections(extra_selections)
