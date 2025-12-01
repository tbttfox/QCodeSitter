from tree_sitter import Point
from typing import Optional


class SyntaxAnalyzer:
    """Provides syntax-aware analysis for smart editing features

    This class uses a shared TreeManager to analyze the syntax tree and provide
    information for features like smart indentation, code completion, etc.
    """

    def __init__(self, tree_manager, document):
        """Initialize the syntax analyzer

        Args:
            tree_manager: The TreeManager instance that owns the parse tree
            document: The TrackedDocument for byte offset calculations
        """
        self.tree_manager = tree_manager
        self.document = document

    def should_indent_after_position(self, line_num: int, col: int) -> bool:
        """Determine if indent should be added after cursor position

        Args:
            line_num: Line number (0-indexed)
            col: Column number (0-indexed, measured in bytes)

        Returns:
            True if an indent should be added, False otherwise
        """
        # Calculate byte offset
        byte_offset = self.document.point_to_byte(Point(line_num, col))

        # Get the node at this position
        node = self.tree_manager.get_node_at_point(byte_offset)

        if node is None:
            return False

        # Walk up the tree to find relevant syntax structures
        current = node
        while current:
            node_type = current.type

            # Check if we're at the end of a compound statement (ends with :)
            # These include: if, for, while, def, class, with, try, except, etc.
            if node_type in (
                "if_statement",
                "for_statement",
                "while_statement",
                "function_definition",
                "class_definition",
                "with_statement",
                "try_statement",
                "except_clause",
                "finally_clause",
                "elif_clause",
                "else_clause",
                "match_statement",
                "case_clause",
            ):
                # Look for a colon child on the same line as the cursor
                # This handles cases like "def foo():  # comment"
                colon_node = self._find_child_by_type(current, ":")
                if colon_node and colon_node.start_point.row == line_num:
                    return True

            # Check for opening brackets/parens
            if node_type in (
                "list",
                "dictionary",
                "set",
                "tuple",
                "argument_list",
                "parameters",
            ):
                # Find the opening and closing brackets for this collection
                opening_bracket = (
                    self._find_child_by_type(current, "(")
                    or self._find_child_by_type(current, "[")
                    or self._find_child_by_type(current, "{")
                )
                closing_bracket = (
                    self._find_child_by_type(current, ")")
                    or self._find_child_by_type(current, "]")
                    or self._find_child_by_type(current, "}")
                )

                # Only indent if:
                # 1. The opening bracket is on the current line
                # 2. The closing bracket is NOT on the current line (bracket is still open)
                if opening_bracket and opening_bracket.start_point.row == line_num:
                    if (
                        not closing_bracket
                        or closing_bracket.start_point.row != line_num
                    ):
                        return True

            current = current.parent

        return False

    def should_dedent_after_position(
        self, line_num: int, col: int, line_text: str
    ) -> bool:
        """Determine if dedent should be applied after cursor position

        Args:
            line_num: Line number (0-indexed)
            col: Column number (0-indexed)
            line_text: The text of the current line

        Returns:
            True if a dedent should be applied, False otherwise
        """
        # Calculate byte offset
        byte_offset = self.document.point_to_byte(Point(line_num, col))

        # Get the node at this position
        node = self.tree_manager.get_node_at_point(byte_offset)

        if node is None:
            return False

        # Walk up to find relevant statement
        current = node
        while current:
            node_type = current.type

            # Check for return statement
            if node_type == "return_statement":
                return True

            # Check for break/continue/pass/raise
            if node_type in (
                "break_statement",
                "continue_statement",
                "pass_statement",
                "raise_statement",
            ):
                return True

            # Check if this line closes a bracket that was opened on a previous line
            # We need to check if the line starts with a closing bracket
            stripped = line_text.lstrip()
            if stripped and stripped[0] in ")]}":
                # Make sure this is actually closing something from earlier
                # by checking if the opening bracket is on a different line
                if current.start_point.row < node.start_point.row:
                    return True

            current = current.parent

        return False

    def _find_child_by_type(self, node, type_name: str):
        """Find a direct child node with the given type

        Args:
            node: The parent node to search
            type_name: The type name to look for

        Returns:
            The first child node matching the type, or None if not found
        """
        for child in node.children:
            if child.type == type_name:
                return child
        return None
