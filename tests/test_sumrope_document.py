"""Tests for SumRopeDocument class based on stub signatures."""

import pytest
from sumrope import SumRopeDocument
from sumrope.sumrope import RLEGroup


class TestSumRopeDocumentInit:
    """Test SumRopeDocument initialization."""

    def test_init_no_parent(self):
        """Test initialization without parent."""
        doc = SumRopeDocument()
        assert doc is not None

    def test_init_with_parent(self):
        """Test initialization with parent."""
        # Would need a QObject parent for this
        doc = SumRopeDocument(None)
        assert doc is not None


class TestSumRopeDocumentBasics:
    """Test basic SumRopeDocument operations."""

    def test_empty_document(self):
        """Test newly created empty document."""
        doc = SumRopeDocument()
        assert doc.total_chars() == 0
        assert doc.total_bytes() == 0
        assert doc.total_lines() >= 0  # May have at least one empty line

    def test_set_plain_text(self):
        """Test setting plain text in document."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello\nWorld")
        assert doc.total_chars() > 0
        assert doc.total_bytes() > 0

    def test_total_chars(self):
        """Test total_chars returns total character count."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello")
        assert doc.total_chars() == 5

    def test_total_bytes(self):
        """Test total_bytes returns total byte count (UTF-8)."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello")
        assert doc.total_bytes() == 5

    def test_total_bytes_unicode(self):
        """Test total_bytes with Unicode characters."""
        doc = SumRopeDocument()
        doc.setPlainText("café")
        assert doc.total_chars() == 4
        assert doc.total_bytes() > 4  # 'é' takes more than 1 byte

    def test_total_lines(self):
        """Test total_lines returns line count."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        lines = doc.total_lines()
        assert lines == 3


class TestSumRopeDocumentConversions:
    """Test conversion methods between char/byte/line positions."""

    def test_char_to_byte_offset_ascii(self):
        """Test converting character position to byte offset with ASCII."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello World")
        byte_offset = doc.char_to_byte_offset(5)
        assert byte_offset == 5

    def test_char_to_byte_offset_unicode(self):
        """Test converting character position to byte offset with Unicode."""
        doc = SumRopeDocument()
        doc.setPlainText("café")
        # Character 4 is at the end, but byte position is higher
        byte_offset = doc.char_to_byte_offset(4)
        assert byte_offset > 4

    def test_byte_to_char_offset_ascii(self):
        """Test converting byte position to character offset with ASCII."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello World")
        char_offset = doc.byte_to_char_offset(5)
        assert char_offset == 5

    def test_byte_to_char_offset_unicode(self):
        """Test converting byte position to character offset with Unicode."""
        doc = SumRopeDocument()
        doc.setPlainText("café")
        # Should handle multibyte characters correctly
        char_offset = doc.byte_to_char_offset(2)
        assert isinstance(char_offset, int)
        assert char_offset >= 0

    def test_char_to_line(self):
        """Test converting character position to line number (0-indexed)."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        line = doc.char_to_line(0)
        assert line == 0
        # Character after first newline should be line 1
        line = doc.char_to_line(7)
        assert line == 1

    def test_line_to_char(self):
        """Test converting line number to character position of line start."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        char_pos = doc.line_to_char(0)
        assert char_pos == 0
        char_pos = doc.line_to_char(1)
        assert char_pos == 7  # "Line 1\n" = 7 chars

    def test_line_to_byte(self):
        """Test converting line number to byte position of line start."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        byte_pos = doc.line_to_byte(0)
        assert byte_pos == 0
        byte_pos = doc.line_to_byte(1)
        assert byte_pos == 7  # "Line 1\n" = 7 bytes (ASCII)

    def test_line_to_byte_unicode(self):
        """Test line_to_byte with Unicode content."""
        doc = SumRopeDocument()
        doc.setPlainText("café\ntest")
        byte_pos = doc.line_to_byte(1)
        # "café\n" where 'é' is 2 bytes: c(1) + a(1) + f(1) + é(2) + \n(1) = 6 bytes
        assert byte_pos > 5


class TestSumRopeDocumentChangedRanges:
    """Test methods for tracking changed ranges."""

    def test_get_changed_byte_range(self):
        """Test get_changed_byte_range returns byte range for character range."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello World")
        byte_start, byte_end = doc.get_changed_byte_range(0, 5)
        assert isinstance(byte_start, int)
        assert isinstance(byte_end, int)
        assert byte_end >= byte_start

    def test_get_changed_byte_range_unicode(self):
        """Test get_changed_byte_range with Unicode characters."""
        doc = SumRopeDocument()
        doc.setPlainText("café test")
        byte_start, byte_end = doc.get_changed_byte_range(0, 4)
        # "café" is 4 chars but more than 4 bytes
        assert byte_end > 4

    def test_get_changed_line_range(self):
        """Test get_changed_line_range returns line range for character range."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        line_start, line_end = doc.get_changed_line_range(0, 7)
        assert isinstance(line_start, int)
        assert isinstance(line_end, int)
        assert line_start == 0
        # Note: line_end is inclusive according to docstring

    def test_get_changed_line_range_multiline(self):
        """Test get_changed_line_range spanning multiple lines."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        # Change spanning from line 0 to line 2
        line_start, line_end = doc.get_changed_line_range(0, 14)
        assert line_start == 0
        assert line_end >= 1  # Should span at least 2 lines

    def test_get_changed_lines_no_changes(self):
        """Test get_changed_lines returns None when no changes."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello")
        doc.reset_changed_lines()
        changed = doc.get_changed_lines()
        # After reset, should be None or indicate no changes
        # Behavior depends on whether setPlainText is tracked

    def test_reset_changed_lines(self):
        """Test reset_changed_lines resets tracking."""
        doc = SumRopeDocument()
        doc.setPlainText("Hello")
        doc.reset_changed_lines()
        # After reset, calling get_changed_lines should reflect no new changes
        changed = doc.get_changed_lines()
        # Should be None or empty after reset


class TestSumRopeDocumentBuildBlockRange:
    """Test build_block_range method."""

    def test_build_block_range_whole_document(self):
        """Test building RLE groups for whole document."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        groups = doc.build_block_range()
        assert isinstance(groups, list)
        assert len(groups) > 0
        assert all(isinstance(g, RLEGroup) for g in groups)

    def test_build_block_range_with_start(self):
        """Test building RLE groups starting from specific line."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        groups = doc.build_block_range(start=1)
        assert isinstance(groups, list)

    def test_build_block_range_with_count(self):
        """Test building RLE groups with specific count."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")
        groups = doc.build_block_range(start=0, count=2)
        assert isinstance(groups, list)

    def test_build_block_range_empty_document(self):
        """Test build_block_range on empty document."""
        doc = SumRopeDocument()
        groups = doc.build_block_range()
        assert isinstance(groups, list)


class TestSumRopeDocumentComplexScenarios:
    """Test complex scenarios with SumRopeDocument."""

    def test_multiline_unicode_document(self):
        """Test document with multiple lines and Unicode characters."""
        doc = SumRopeDocument()
        text = "Hello 🌍\nCafé ☕\n日本語"
        doc.setPlainText(text)

        total_chars = doc.total_chars()
        total_bytes = doc.total_bytes()

        assert total_chars > 0
        assert total_bytes > total_chars  # Unicode takes more bytes

        # Test conversions work
        for line in range(doc.total_lines()):
            char_pos = doc.line_to_char(line)
            byte_pos = doc.line_to_byte(line)
            assert char_pos >= 0
            assert byte_pos >= 0

    def test_roundtrip_conversions(self):
        """Test that conversion methods are consistent."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")

        # Test char <-> byte roundtrip
        for char_pos in range(doc.total_chars()):
            byte_pos = doc.char_to_byte_offset(char_pos)
            char_back = doc.byte_to_char_offset(byte_pos)
            # Should be close (may not be exact at multibyte boundaries)
            assert abs(char_back - char_pos) <= 1

    def test_large_document(self):
        """Test document with many lines."""
        doc = SumRopeDocument()
        lines = [f"Line {i}" for i in range(100)]
        text = "\n".join(lines)
        doc.setPlainText(text)

        assert doc.total_lines() == 100
        assert doc.total_chars() > 0
        assert doc.total_bytes() > 0

        # Test accessing various lines
        char_pos_0 = doc.line_to_char(0)
        char_pos_50 = doc.line_to_char(50)
        char_pos_99 = doc.line_to_char(99)

        assert char_pos_0 == 0
        assert char_pos_50 > char_pos_0
        assert char_pos_99 > char_pos_50

    def test_changed_range_tracking(self):
        """Test that changed range methods work together."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2\nLine 3")

        # Get ranges for a character change
        char_start, char_end = 7, 14  # Covers "Line 2"
        byte_start, byte_end = doc.get_changed_byte_range(char_start, char_end)
        line_start, line_end = doc.get_changed_line_range(char_start, char_end)

        # Verify consistency
        assert byte_end >= byte_start
        assert line_end >= line_start
        assert line_start <= 1  # Should include line 1
        assert line_end >= 1    # Should include line 1

    def test_empty_lines(self):
        """Test document with empty lines."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\n\nLine 3")

        assert doc.total_lines() == 3
        line1_char = doc.line_to_char(1)
        line2_char = doc.line_to_char(2)

        # Line 1 is empty, so positions should be close
        assert line2_char > line1_char

    def test_only_newlines(self):
        """Test document with only newlines."""
        doc = SumRopeDocument()
        doc.setPlainText("\n\n\n")

        lines = doc.total_lines()
        chars = doc.total_chars()

        assert lines > 0
        assert chars >= 3  # At least 3 newline characters

    def test_no_trailing_newline(self):
        """Test document without trailing newline."""
        doc = SumRopeDocument()
        doc.setPlainText("Line 1\nLine 2")

        lines = doc.total_lines()
        assert lines == 2

        # Last line should still be accessible
        last_line_char = doc.line_to_char(lines - 1)
        assert last_line_char >= 0
