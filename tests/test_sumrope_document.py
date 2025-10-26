import pytest
from Qt.QtWidgets import QApplication
from Qt.QtGui import QTextCursor
from sumrope.sumrope_document import SumRopeDocument


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def doc(qapp):
    """Create a fresh SumRopeDocument for each test."""
    return SumRopeDocument()


def test_empty_document(doc):
    """Test that empty document initializes correctly."""
    assert doc.total_chars() == 0
    assert doc.total_bytes() == 0
    assert doc.total_lines() == 1  # Empty doc still has 1 line


def test_initial_text(qapp):
    """Test document initialized with text."""
    doc = SumRopeDocument()
    doc.setPlainText("Hello\nWorld")

    assert doc.total_chars() == 11
    assert doc.total_bytes() == 11  # ASCII chars are 1 byte each
    assert doc.total_lines() == 2


def test_char_to_byte_offset_ascii(qapp):
    """Test character to byte offset conversion with ASCII text."""
    doc = SumRopeDocument()
    doc.setPlainText("Hello World")

    assert doc.char_to_byte_offset(0) == 0
    assert doc.char_to_byte_offset(5) == 5
    assert doc.char_to_byte_offset(11) == 11


def test_char_to_byte_offset_unicode(qapp):
    """Test character to byte offset conversion with Unicode text."""
    doc = SumRopeDocument()
    # "Hello 世界" - where 世 and 界 are 3 bytes each in UTF-8
    doc.setPlainText("Hello 世界")

    assert doc.char_to_byte_offset(0) == 0
    assert doc.char_to_byte_offset(6) == 6  # Before first Chinese char
    assert doc.char_to_byte_offset(7) == 9  # After first Chinese char (6 + 3)
    assert doc.char_to_byte_offset(8) == 12  # After second Chinese char (9 + 3)


def test_char_to_line(qapp):
    """Test character to line conversion."""
    doc = SumRopeDocument()
    doc.setPlainText("Line 1\nLine 2\nLine 3")

    assert doc.char_to_line(0) == 0  # Start of line 1
    assert doc.char_to_line(6) == 0  # At first newline
    assert doc.char_to_line(7) == 1  # Start of line 2
    assert doc.char_to_line(14) == 2  # Start of line 3


def test_line_to_char(qapp):
    """Test line to character position conversion."""
    doc = SumRopeDocument()
    doc.setPlainText("Line 1\nLine 2\nLine 3")

    assert doc.line_to_char(0) == 0  # Start of line 1
    assert doc.line_to_char(1) == 7  # Start of line 2 (after "Line 1\n")
    assert doc.line_to_char(2) == 14  # Start of line 3


def test_insert_text(qapp):
    """Test inserting text updates ropes correctly."""
    doc = SumRopeDocument()
    doc.setPlainText("Hello World")

    # Insert " Beautiful" at position 5
    cursor = QTextCursor(doc)
    cursor.setPosition(5)
    cursor.insertText(" Beautiful")

    assert doc.toPlainText() == "Hello Beautiful World"
    assert doc.total_chars() == 21
    assert doc.total_bytes() == 21


def test_delete_text(qapp):
    """Test deleting text updates ropes correctly."""
    doc = SumRopeDocument()
    doc.setPlainText("Hello Beautiful World")

    # Delete " Beautiful" (10 chars starting at position 5)
    cursor = QTextCursor(doc)
    cursor.setPosition(5)
    cursor.setPosition(15, QTextCursor.KeepAnchor)
    cursor.removeSelectedText()

    assert doc.toPlainText() == "Hello World"
    assert doc.total_chars() == 11
    assert doc.total_bytes() == 11


def test_replace_text(qapp):
    """Test replacing text updates ropes correctly."""
    doc = SumRopeDocument()
    doc.setPlainText("Hello World")

    # Replace "World" with "Python"
    cursor = QTextCursor(doc)
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.KeepAnchor)
    cursor.insertText("Python")

    assert doc.toPlainText() == "Hello Python"
    assert doc.total_chars() == 12
    assert doc.total_bytes() == 12


def test_insert_newlines(qapp):
    """Test inserting newlines updates line tracking."""
    doc = SumRopeDocument()
    doc.setPlainText("HelloWorld")

    # Insert newline at position 5
    cursor = QTextCursor(doc)
    cursor.setPosition(5)
    cursor.insertText("\n")

    assert doc.total_lines() == 2
    assert doc.char_to_line(0) == 0
    assert doc.char_to_line(6) == 1


def test_get_changed_byte_range(qapp):
    """Test getting byte range for character range."""
    doc = SumRopeDocument()
    doc.setPlainText("Hello 世界 World")

    # Character range 0-6 should be bytes 0-6
    byte_start, byte_end = doc.get_changed_byte_range(0, 6)
    assert byte_start == 0
    assert byte_end == 6

    # Character range 6-8 includes two 3-byte chars
    byte_start, byte_end = doc.get_changed_byte_range(6, 8)
    assert byte_start == 6
    assert byte_end == 12


def test_get_changed_line_range(qapp):
    """Test getting line range for character range."""
    doc = SumRopeDocument()
    doc.setPlainText("Line 1\nLine 2\nLine 3\nLine 4")

    # Changes within first line
    line_start, line_end = doc.get_changed_line_range(0, 5)
    assert line_start == 0
    assert line_end == 0

    # Changes spanning lines 1 and 2
    line_start, line_end = doc.get_changed_line_range(0, 10)
    assert line_start == 0
    assert line_end == 1

    # Changes on line 3
    line_start, line_end = doc.get_changed_line_range(14, 20)
    assert line_start == 2
    assert line_end == 2


def test_multiple_edits(qapp):
    """Test multiple edits maintain consistency."""
    doc = SumRopeDocument()
    doc.setPlainText("A\nB\nC")

    cursor = QTextCursor(doc)

    # Insert at beginning
    cursor.setPosition(0)
    cursor.insertText("Start\n")

    assert doc.total_lines() == 4
    assert doc.total_chars() == 11

    # Insert at end
    cursor.movePosition(QTextCursor.End)
    cursor.insertText("\nEnd")

    assert doc.total_lines() == 5
    assert doc.total_chars() == 15

    # Delete from middle (removes "A\nB\n" which is 4 chars including 2 newlines)
    cursor.setPosition(6)
    cursor.setPosition(10, QTextCursor.KeepAnchor)
    cursor.removeSelectedText()

    # After delete: "Start\nC\nEnd" which has 2 newlines = 3 lines
    assert doc.total_lines() == 3
    assert doc.total_chars() == 11


def test_unicode_multi_byte_characters(qapp):
    """Test with various Unicode characters of different byte lengths."""
    doc = SumRopeDocument()
    # Euro (€) = 3 bytes, Emoji (😀) = 4 bytes, ASCII = 1 byte
    doc.setPlainText("A€😀Z")

    assert doc.total_chars() == 4
    assert doc.total_bytes() == 1 + 3 + 4 + 1  # 9 bytes total

    assert doc.char_to_byte_offset(0) == 0  # 'A'
    assert doc.char_to_byte_offset(1) == 1  # '€' starts at byte 1
    assert doc.char_to_byte_offset(2) == 4  # '😀' starts at byte 4
    assert doc.char_to_byte_offset(3) == 8  # 'Z' starts at byte 8


def test_empty_line_handling(qapp):
    """Test handling of empty lines."""
    doc = SumRopeDocument()
    doc.setPlainText("A\n\nB")

    assert doc.total_lines() == 3
    assert doc.line_to_char(0) == 0
    assert doc.line_to_char(1) == 2  # After first \n
    assert doc.line_to_char(2) == 3  # After second \n
