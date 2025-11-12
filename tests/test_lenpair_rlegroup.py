"""Tests for LenPair and RLEGroup classes based on stub signatures."""

import pytest
from sumrope import SumRope


class TestLenPair:
    """Tests for the LenPair class - a tuple-ish group of integers that can be added and subtracted."""

    def test_init_with_none(self):
        """Test initialization with None."""
        from sumrope.sumrope import LenPair
        pair = LenPair(None)
        assert hasattr(pair, 'charlen')
        assert hasattr(pair, 'bytelen')

    def test_init_with_list(self):
        """Test initialization with a list of integers."""
        from sumrope.sumrope import LenPair
        pair = LenPair([10, 20])
        assert pair.charlen == 10
        assert pair.bytelen == 20

    def test_init_with_lenpair(self):
        """Test initialization with another LenPair."""
        from sumrope.sumrope import LenPair
        original = LenPair([5, 8])
        copy = LenPair(original)
        assert copy.charlen == original.charlen
        assert copy.bytelen == original.bytelen

    def test_getitem(self):
        """Test accessing values by index."""
        from sumrope.sumrope import LenPair
        pair = LenPair([15, 25])
        assert pair[0] == 15
        assert pair[1] == 25

    def test_add(self):
        """Test addition of two LenPairs."""
        from sumrope.sumrope import LenPair
        pair1 = LenPair([10, 20])
        pair2 = LenPair([5, 8])
        result = pair1 + pair2
        assert isinstance(result, LenPair)
        assert result.charlen == 15
        assert result.bytelen == 28

    def test_sub(self):
        """Test subtraction of two LenPairs."""
        from sumrope.sumrope import LenPair
        pair1 = LenPair([10, 20])
        pair2 = LenPair([5, 8])
        result = pair1 - pair2
        assert isinstance(result, LenPair)
        assert result.charlen == 5
        assert result.bytelen == 12


class TestRLEGroup:
    """Tests for RLEGroup - keeps track of each character's length in bytes (RLE encoded)."""

    def test_init_with_none(self):
        """Test initialization with None."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup(None)
        assert hasattr(group, 'encoding')
        assert hasattr(group, 'pattern')
        assert hasattr(group, 'rle')
        assert hasattr(group, 'charlen')
        assert hasattr(group, 'bytelen')

    def test_init_with_ascii_text(self):
        """Test initialization with ASCII text."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("hello")
        assert group.charlen == 5
        assert group.bytelen == 5  # ASCII characters are 1 byte each

    def test_init_with_unicode_text(self):
        """Test initialization with Unicode text."""
        from sumrope.sumrope import RLEGroup
        # Unicode character that takes multiple bytes
        group = RLEGroup("café")
        assert group.charlen == 4
        assert group.bytelen > 4  # 'é' takes more than 1 byte in UTF-8

    def test_init_with_multibyte_unicode(self):
        """Test initialization with multi-byte Unicode characters."""
        from sumrope.sumrope import RLEGroup
        # Emoji takes multiple bytes
        group = RLEGroup("Hello 🌍")
        assert group.charlen == 8  # 7 characters including space and emoji
        assert group.bytelen > 8  # Emoji takes multiple bytes

    def test_byte_to_char_ascii(self):
        """Test converting byte offset to character offset with ASCII."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("hello")
        assert group.byte_to_char(0) == 0
        assert group.byte_to_char(2) == 2
        assert group.byte_to_char(5) == 5

    def test_byte_to_char_unicode(self):
        """Test converting byte offset to character offset with Unicode."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("café")
        # This test ensures the method exists and returns reasonable values
        result = group.byte_to_char(2)
        assert isinstance(result, int)
        assert result >= 0

    def test_char_to_byte_ascii(self):
        """Test converting character offset to byte offset with ASCII."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("hello")
        assert group.char_to_byte(0) == 0
        assert group.char_to_byte(2) == 2
        assert group.char_to_byte(5) == 5

    def test_char_to_byte_unicode(self):
        """Test converting character offset to byte offset with Unicode."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("café")
        result = group.char_to_byte(2)
        assert isinstance(result, int)
        assert result >= 0

    def test_byte_to_pair(self):
        """Test converting byte offset to LenPair."""
        from sumrope.sumrope import RLEGroup, LenPair
        group = RLEGroup("hello world")
        result = group.byte_to_pair(5)
        assert isinstance(result, LenPair)
        assert result.charlen >= 0
        assert result.bytelen >= 0

    def test_char_to_pair(self):
        """Test converting character offset to LenPair."""
        from sumrope.sumrope import RLEGroup, LenPair
        group = RLEGroup("hello world")
        result = group.char_to_pair(5)
        assert isinstance(result, LenPair)
        assert result.charlen >= 0
        assert result.bytelen >= 0

    def test_rle_structure(self):
        """Test that RLE structure contains tuples of (count, bytes_per_char)."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("aaa")
        assert isinstance(group.rle, list)
        # RLE should compress repeated characters
        if len(group.rle) > 0:
            assert isinstance(group.rle[0], tuple)
            assert len(group.rle[0]) == 2

    def test_empty_string(self):
        """Test initialization with empty string."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("")
        assert group.charlen == 0
        assert group.bytelen == 0

    def test_mixed_byte_lengths(self):
        """Test text with mixed byte-length characters."""
        from sumrope.sumrope import RLEGroup
        # Mix of 1-byte (ASCII), 2-byte, and 4-byte (emoji) characters
        group = RLEGroup("a£€🌍")
        assert group.charlen == 4
        # 'a' = 1 byte, '£' = 2 bytes, '€' = 3 bytes, '🌍' = 4 bytes
        expected_bytes = 1 + 2 + 3 + 4
        assert group.bytelen == expected_bytes

    def test_byte_char_roundtrip(self):
        """Test that byte_to_char and char_to_byte are inverse operations."""
        from sumrope.sumrope import RLEGroup
        group = RLEGroup("hello world")
        for char_pos in range(group.charlen + 1):
            byte_pos = group.char_to_byte(char_pos)
            char_back = group.byte_to_char(byte_pos)
            assert char_back == char_pos
