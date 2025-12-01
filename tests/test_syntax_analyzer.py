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


# fmt: off
@pytest.mark.parametrize(
    "source, point, should",
    [
        pytest.param("def foo():\n",            (0, 9),  True,  id="indent_after_function_definition"),
        pytest.param("if x:\n",                 (0, 4),  True,  id="indent_after_if_statement"),
        pytest.param("for i in range(10):\n",   (0, 18), True,  id="indent_after_for_loop"),
        pytest.param("while True:\n",           (0, 10), True,  id="indent_after_while_loop"),
        pytest.param("class Foo:\n",            (0, 9),  True,  id="indent_after_class_definition"),
        pytest.param("items = [\n",             (0, 8),  True,  id="indent_after_open_bracket"),  # Position at '['
        pytest.param("result = foo(\n",         (0, 12), True,  id="indent_after_open_paren"),    # Position at '('
        pytest.param("def foo():  # comment\n", (0, 9),  True,  id="indent_after_function_with_comment"),
        pytest.param("print(42)\n",             (0, 8),  False, id="no_indent_after_closed_bracket"),
        pytest.param("x = 42\n",                (0, 5),  False, id="no_indent_on_regular_line"),
    ],
)
def test_indent(source, point, should):
    analyzer, _doc = create_analyzer(source)
    should_indent = analyzer.should_indent_after_position(*point)
    assert should_indent is should

@pytest.mark.parametrize(
    "source, point, should",
    [
        pytest.param("def foo():\n    return 42\n", (1, 10), True,  id="dedent_after_return"),     # Position at end of 'return'
        pytest.param("def foo():\n    pass\n",      (1, 7),  True,  id="dedent_after_pass"),       # Position at end of 'pass'
        pytest.param("while True:\n    break\n",    (1, 8),  True,  id="dedent_after_break"),      # Position at end of 'break'
        pytest.param("while True:\n    continue\n", (1, 11), True,  id="dedent_after_continue"),   # Position at end of 'continue'
        pytest.param("x = 42\n",                    (0, 5),  False, id="no_dedent_on_regular_line"),
    ],
)
def test_dedent(source, point, should):
    analyzer, _doc = create_analyzer(source)
    lastline = source.split("\n")[-2]
    should_dedent = analyzer.should_dedent_after_position(point[0], point[1], lastline)
    assert should_dedent is should
