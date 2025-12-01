import pytest
from tree_sitter import Language, Point
import tree_sitter_python as tspython
from sumrope.tree_manager import TreeManager
from sumrope.syntax_analyzer import SyntaxAnalyzer


class MockDocument:
    """Mock TrackedDocument for testing"""

    def __init__(self, source_text: str):
        self.source_bytes = source_text.encode()
        self.lines = source_text.split("\n")

    def point_to_byte(self, point: Point) -> int:
        """Convert a Point to byte offset"""
        byte_offset = 0
        for i in range(point.row):
            byte_offset += len(self.lines[i].encode()) + 1  # +1 for newline
        byte_offset += point.column
        return byte_offset


def create_analyzer(source_text: str):
    """Helper to create a TreeManager and SyntaxAnalyzer"""
    document = MockDocument(source_text)
    language = Language(tspython.language())

    def source_callback(byte_offset: int, point: Point) -> bytes:
        return document.source_bytes[byte_offset:]

    tree_manager = TreeManager(language, source_callback)

    # Initial parse
    tree_manager.update(
        start_byte=0,
        old_end_byte=0,
        new_end_byte=len(document.source_bytes),
        start_point=Point(0, 0),
        old_end_point=Point(0, 0),
        new_end_point=Point(len(document.lines) - 1, len(document.lines[-1])),
    )

    analyzer = SyntaxAnalyzer(tree_manager, document)
    return analyzer, document


@pytest.mark.parametrize(
    "source, point, should",
    [
        ("def foo():\n", (0, 9), True),
        ("if x:\n", (0, 4), True),
        ("for i in range(10):\n", (0, 18), True),
        ("while True:\n", (0, 10), True),
        ("class Foo:\n", (0, 9), True),
        ("items = [\n", (0, 8), True),
        ("result = foo(\n", (0, 12), True),
        ("def foo():  # comment\n", (0, 9), True),
        ("print(42)\n", (0, 8), False),
        ("x = 42\n", (0, 5), False),
    ],
)
def test_indent_after(source, point, should):
    analyzer, _doc = create_analyzer(source)
    should_indent = analyzer.should_indent_after_position(*point)
    assert should_indent is should


@pytest.mark.parametrize(
    "source, point, should",
    [
        ("def foo():\n    return 42\n", (1, 13), True),
        ("def foo():\n    pass\n", (1, 8), True),
        ("while True:\n    break\n", (1, 9), True),
        ("while True:\n    continue\n", (1, 12), True),
        ("x = 42\n", (0, 5), False),
    ],
)
def test_dedent_after(source, point, should):
    analyzer, _doc = create_analyzer(source)
    lastline = source.split("\n")[-2]
    should_dedent = analyzer.should_dedent_after_position(point[0], point[1], lastline)
    assert should_dedent is should
