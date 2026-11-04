"""Tests for the text helpers and the multi-cursor clipboard format"""

from __future__ import annotations

import pytest
from Qt import QtCore

from QCodeSitter.cursors.clipboard import (
    MIME,
    encode_multi_copy,
    indent_tabs_to_spaces,
    split_multi_copy,
)
from QCodeSitter.tracked_document import len16, utf16_to_index
from QCodeSitter.utils import dedent_string, leading_whitespace


class TestUtils:
    def test_len16(self):
        assert len16("a🎉") == 3

    def test_utf16_to_index(self):
        assert utf16_to_index("a🎉b", 3) == 2
        # Inside the surrogate pair rounds down
        assert utf16_to_index("a🎉b", 2) == 1

    @pytest.mark.parametrize(
        "indent, tabs, expected",
        [
            ("        ", False, "    "),
            ("  ", False, ""),
            ("\t\t", True, "\t"),
            ("  ", True, "  "),
        ],
    )
    def test_dedent_string(self, indent, tabs, expected):
        assert dedent_string(indent, tabs, 4) == expected


class TestClipboardFormat:
    def test_round_trip(self, qapp):
        data = encode_multi_copy(["one", "", "three\nlines"])
        assert data.text() == "one\n\nthree\nlines"
        assert split_multi_copy(data, 3) == ["one", "", "three\nlines"]

    def test_cursor_count_mismatch(self, qapp):
        assert split_multi_copy(encode_multi_copy(["a", "b"]), 3) is None

    def test_plain_text(self, qapp):
        data = QtCore.QMimeData()
        data.setText("a\nb")
        assert split_multi_copy(data, 2) is None

    def test_indent_tabs_to_spaces(self):
        assert indent_tabs_to_spaces("\t\tx\n\ty\tz", 2) == "    x\n  y\tz"


class TestLeadingWhitespace:
    @pytest.mark.parametrize(
        "line, indent", [("    x", "    "), ("\t x", "\t "), ("x", ""), ("   ", "   ")]
    )
    def test_leading_whitespace(self, line, indent):
        assert leading_whitespace(line) == indent


class TestMalformedClipboard:
    @pytest.mark.parametrize("lengths", [b"1,x", b"", b"\xff\xfe"])
    def test_unreadable_lengths_are_plain_text(self, qapp, lengths):
        """Another program can put anything in our format, which pastes as plain text"""
        data = QtCore.QMimeData()
        data.setData(MIME, lengths)
        data.setText("a b")
        assert split_multi_copy(data, 2) is None
