"""Tests for the bracket and quote matching highlight"""

from __future__ import annotations

import pytest

from QCodeSitter.behaviors.auto_bracket import AutoBracket
from QCodeSitter.behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from tests.helpers import set_cursor_position


def highlighted(editor) -> list[str]:
    """The text of each bracket highlight, in the order they were added"""
    return [
        sel.cursor.selectedText()
        for sel in editor.selections(HighlightMatchingBrackets.SOURCE)
    ]


def highlighted_ranges(editor) -> list[tuple[int, int]]:
    return [
        (sel.cursor.selectionStart(), sel.cursor.selectionEnd())
        for sel in editor.selections(HighlightMatchingBrackets.SOURCE)
    ]


@pytest.fixture
def bracket_editor(editor):
    editor.remove_behavior(AutoBracket)
    return editor


class TestBracketMatching:
    @pytest.mark.parametrize(
        "text, cursor, expected",
        [
            # After an opening bracket
            ("foo(a, b)", 4, [(3, 4), (8, 9)]),
            # Before an opening bracket
            ("foo(a, b)", 3, [(3, 4), (8, 9)]),
            # After a closing bracket
            ("x = [1, 2]", 10, [(9, 10), (4, 5)]),
            ("d = {'a': (1)}", 14, [(13, 14), (4, 5)]),
            # Nested brackets match their own pair
            ("f(g(x))", 4, [(3, 4), (5, 6)]),
            # In broken code, the brackets are siblings in an ERROR node, and the
            # nearest balanced one matches instead of the first one
            ("(a(a = )", 8, [(7, 8), (2, 3)]),
        ],
    )
    def test_matching_pair(self, bracket_editor, text, cursor, expected):
        bracket_editor.setPlainText(text)
        set_cursor_position(bracket_editor, cursor)
        assert highlighted_ranges(bracket_editor) == expected

    def test_unmatched_bracket(self, bracket_editor):
        bracket_editor.setPlainText("foo(a")
        set_cursor_position(bracket_editor, 4)
        assert highlighted(bracket_editor) == []

    def test_no_bracket_near_cursor(self, bracket_editor):
        bracket_editor.setPlainText("foo(a, b)")
        set_cursor_position(bracket_editor, 6)
        assert highlighted(bracket_editor) == []

    def test_after_surrogate_pair(self, bracket_editor):
        """Positions are UTF-16, so an emoji takes two code units"""
        text = 'x = "🎉" + (1)'
        bracket_editor.setPlainText(text)
        set_cursor_position(bracket_editor, 11)
        assert highlighted(bracket_editor) == ["(", ")"]

    def test_bracket_pairs_option(self, bracket_editor):
        bracket_editor.options["highlight_bracket_pairs"] = ["()"]
        bracket_editor.setPlainText("x = [1]")
        set_cursor_position(bracket_editor, 5)
        assert highlighted(bracket_editor) == []


class TestQuoteMatching:
    @pytest.mark.parametrize(
        "text, cursor, expected",
        [
            ('x = "abc"', 5, ['"', '"']),
            ("x = 'abc'", 9, ["'", "'"]),
            ('x = """doc"""', 7, ['"""', '"""']),
            ('x = f"{y}"', 6, ['f"', '"']),
        ],
    )
    def test_matching_quotes(self, bracket_editor, text, cursor, expected):
        bracket_editor.setPlainText(text)
        set_cursor_position(bracket_editor, cursor)
        assert highlighted(bracket_editor) == expected

    def test_quote_pairs_option(self, bracket_editor):
        """Turning off a quote character stops it from being matched"""
        bracket_editor.options["highlight_quote_chars"] = "'"
        bracket_editor.setPlainText('x = "abc"')
        set_cursor_position(bracket_editor, 5)
        assert highlighted(bracket_editor) == []

    def test_removed_behavior_clears(self, bracket_editor):
        bracket_editor.setPlainText('x = "abc"')
        set_cursor_position(bracket_editor, 5)
        bracket_editor.remove_behavior(HighlightMatchingBrackets)
        assert highlighted(bracket_editor) == []
