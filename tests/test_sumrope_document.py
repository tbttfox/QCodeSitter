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
        # Empty document should have at least basic structure
        assert doc.total_lines() >= 0

    def test_total_methods_exist(self):
        """Test that total_* methods exist and return integers."""
        doc = SumRopeDocument()
        assert isinstance(doc.total_chars(), int)
        assert isinstance(doc.total_bytes(), int)
        assert isinstance(doc.total_lines(), int)


class TestSumRopeDocumentConversions:
    """Test conversion methods between char/byte/line positions."""

    def test_char_to_byte_offset_exists(self):
        """Test that char_to_byte_offset method exists and returns int."""
        doc = SumRopeDocument()
        result = doc.char_to_byte_offset(0)
        assert isinstance(result, int)

    def test_byte_to_char_offset_exists(self):
        """Test that byte_to_char_offset method exists and returns int."""
        doc = SumRopeDocument()
        result = doc.byte_to_char_offset(0)
        assert isinstance(result, int)

    def test_char_to_line_exists(self):
        """Test that char_to_line method exists and returns int."""
        doc = SumRopeDocument()
        result = doc.char_to_line(0)
        assert isinstance(result, int)
        assert result >= 0

    def test_line_to_char_exists(self):
        """Test that line_to_char method exists and returns int."""
        doc = SumRopeDocument()
        result = doc.line_to_char(0)
        assert isinstance(result, int)
        assert result >= 0

    def test_line_to_byte_exists(self):
        """Test that line_to_byte method exists and returns int."""
        doc = SumRopeDocument()
        result = doc.line_to_byte(0)
        assert isinstance(result, int)
        assert result >= 0


class TestSumRopeDocumentChangedRanges:
    """Test methods for tracking changed ranges."""

    def test_get_changed_byte_range_exists(self):
        """Test get_changed_byte_range method exists and returns tuple."""
        doc = SumRopeDocument()
        byte_start, byte_end = doc.get_changed_byte_range(0, 0)
        assert isinstance(byte_start, int)
        assert isinstance(byte_end, int)

    def test_get_changed_line_range_exists(self):
        """Test get_changed_line_range method exists and returns tuple."""
        doc = SumRopeDocument()
        line_start, line_end = doc.get_changed_line_range(0, 0)
        assert isinstance(line_start, int)
        assert isinstance(line_end, int)

    def test_get_changed_lines_exists(self):
        """Test get_changed_lines method exists."""
        doc = SumRopeDocument()
        result = doc.get_changed_lines()
        # Should be None or tuple of two ints
        assert result is None or (isinstance(result, tuple) and len(result) == 2)

    def test_reset_changed_lines_exists(self):
        """Test reset_changed_lines method exists and can be called."""
        doc = SumRopeDocument()
        doc.reset_changed_lines()  # Should not raise


class TestSumRopeDocumentBuildBlockRange:
    """Test build_block_range method."""

    def test_build_block_range_default(self):
        """Test building RLE groups with default parameters."""
        doc = SumRopeDocument()
        groups = doc.build_block_range()
        assert isinstance(groups, list)
        # All items should be RLEGroup instances
        assert all(isinstance(g, RLEGroup) for g in groups)

    def test_build_block_range_with_params(self):
        """Test building RLE groups with custom start and count."""
        doc = SumRopeDocument()
        groups = doc.build_block_range(start=0, count=1)
        assert isinstance(groups, list)
