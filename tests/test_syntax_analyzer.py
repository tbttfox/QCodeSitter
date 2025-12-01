import pytest
from tree_sitter import Language, Point
import tree_sitter_python as tspython
from sumrope.tree_manager import TreeManager
from sumrope.syntax_analyzer import SyntaxAnalyzer


class MockDocument:
    """Mock TrackedDocument for testing"""

    def __init__(self, source_text: str):
        self.source_text = source_text.encode()
        self.lines = source_text.split('\n')

    def point_to_byte(self, point: Point) -> int:
        """Convert a Point to byte offset"""
        byte_offset = 0
        for i in range(point.row):
            byte_offset += len(self.lines[i].encode()) + 1  # +1 for newline
        byte_offset += point.column
        return byte_offset


class TestSyntaxAnalyzer:
    """Tests for the SyntaxAnalyzer class"""

    def create_analyzer(self, source_text: str):
        """Helper to create a TreeManager and SyntaxAnalyzer"""
        document = MockDocument(source_text)
        language = Language(tspython.language())

        def source_callback(byte_offset: int, point: Point) -> bytes:
            return document.source_text[byte_offset:]

        tree_manager = TreeManager(language, source_callback)

        # Initial parse
        tree_manager.update(
            start_byte=0,
            old_end_byte=0,
            new_end_byte=len(document.source_text),
            start_point=Point(0, 0),
            old_end_point=Point(0, 0),
            new_end_point=Point(len(document.lines) - 1, len(document.lines[-1]))
        )

        analyzer = SyntaxAnalyzer(tree_manager, document)
        return analyzer, document

    def test_indent_after_function_definition(self):
        """Test indent detection after function definition"""
        source = "def foo():\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the colon
        should_indent = analyzer.should_indent_after_position(0, 9)
        assert should_indent is True

    def test_indent_after_if_statement(self):
        """Test indent detection after if statement"""
        source = "if x:\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the colon
        should_indent = analyzer.should_indent_after_position(0, 4)
        assert should_indent is True

    def test_indent_after_for_loop(self):
        """Test indent detection after for loop"""
        source = "for i in range(10):\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the colon
        should_indent = analyzer.should_indent_after_position(0, 18)
        assert should_indent is True

    def test_indent_after_while_loop(self):
        """Test indent detection after while loop"""
        source = "while True:\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the colon
        should_indent = analyzer.should_indent_after_position(0, 10)
        assert should_indent is True

    def test_indent_after_class_definition(self):
        """Test indent detection after class definition"""
        source = "class Foo:\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the colon
        should_indent = analyzer.should_indent_after_position(0, 9)
        assert should_indent is True

    def test_indent_after_open_bracket(self):
        """Test indent detection after opening bracket"""
        source = "items = [\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the open bracket
        should_indent = analyzer.should_indent_after_position(0, 8)
        assert should_indent is True

    def test_no_indent_after_closed_bracket(self):
        """Test no indent when bracket is opened and closed on same line"""
        source = "print(42)\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the closing paren - should not indent
        should_indent = analyzer.should_indent_after_position(0, 8)
        assert should_indent is False

    def test_indent_after_open_paren(self):
        """Test indent detection after opening paren"""
        source = "result = foo(\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the open paren
        should_indent = analyzer.should_indent_after_position(0, 12)
        assert should_indent is True

    def test_indent_after_function_with_comment(self):
        """Test indent detection after function with trailing comment"""
        source = "def foo():  # comment\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position after the colon (before comment)
        should_indent = analyzer.should_indent_after_position(0, 9)
        assert should_indent is True

    def test_dedent_after_return(self):
        """Test dedent detection after return statement"""
        source = "def foo():\n    return 42\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position at end of return statement
        should_dedent = analyzer.should_dedent_after_position(1, 13, "    return 42")
        assert should_dedent is True

    def test_dedent_after_pass(self):
        """Test dedent detection after pass statement"""
        source = "def foo():\n    pass\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position at end of pass statement
        should_dedent = analyzer.should_dedent_after_position(1, 8, "    pass")
        assert should_dedent is True

    def test_dedent_after_break(self):
        """Test dedent detection after break statement"""
        source = "while True:\n    break\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position at end of break statement
        should_dedent = analyzer.should_dedent_after_position(1, 9, "    break")
        assert should_dedent is True

    def test_dedent_after_continue(self):
        """Test dedent detection after continue statement"""
        source = "while True:\n    continue\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position at end of continue statement
        should_dedent = analyzer.should_dedent_after_position(1, 12, "    continue")
        assert should_dedent is True

    def test_no_indent_on_regular_line(self):
        """Test no indent on regular assignment"""
        source = "x = 42\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position at end of line
        should_indent = analyzer.should_indent_after_position(0, 5)
        assert should_indent is False

    def test_no_dedent_on_regular_line(self):
        """Test no dedent on regular line"""
        source = "x = 42\n"
        analyzer, doc = self.create_analyzer(source)

        # Check position at end of line
        should_dedent = analyzer.should_dedent_after_position(0, 5, "x = 42")
        assert should_dedent is False
