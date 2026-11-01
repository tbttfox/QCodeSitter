"""Tests for the gutter layout and the line number gutter"""

from __future__ import annotations

import pytest
from Qt import QtGui

from QCodeSitter.behaviors.code_folding import (
    FoldingGutterArea,
)
from QCodeSitter.behaviors.line_numbers import LineNumber, LineNumberArea
from QCodeSitter.gutters import GutterWidget


def gutter_widths(editor) -> list[int]:
    return [gutter.reserved_width for gutter in editor.gutters]


class TestLineNumbers:
    """Test line number display behavior."""

    def test_gutter_width_grows_with_digits(self, editor, qtbot):
        """The line number gutter widens when the line count needs another digit"""
        area = editor.get_behavior(LineNumber).line_number_area
        editor.setPlainText("\n" * 8)
        narrow = area.reserved_width
        editor.setPlainText("\n" * 120)
        assert area.reserved_width > narrow
        assert editor.viewportMargins().left() == sum(gutter_widths(editor))

    def test_remove_gives_back_space(self, editor, qtbot):
        area = editor.get_behavior(LineNumber).line_number_area
        editor.remove_behavior(LineNumber)
        assert area not in editor.gutters
        assert editor.viewportMargins().left() == sum(gutter_widths(editor))

    def test_readding_does_not_duplicate(self, editor, qtbot):
        editor.remove_behavior(LineNumber)
        editor.add_behavior(LineNumber)
        editor.add_behavior(LineNumber)
        assert [type(g) for g in editor.gutters] == [FoldingGutterArea, LineNumberArea]
        assert editor.viewportMargins().left() == sum(gutter_widths(editor))


class TestGutterWidget:
    def test_gutters_lay_out_in_order(self, editor):
        numbers, folds = editor.gutters
        assert isinstance(numbers, LineNumberArea)
        assert isinstance(folds, FoldingGutterArea)
        left = editor.contentsRect().left()
        assert numbers.geometry().left() == left
        assert folds.geometry().left() == left + numbers.reserved_width
        assert editor.viewportMargins().left() == sum(gutter_widths(editor))

    def test_visible_blocks(self, editor):
        editor.setPlainText("a\nb\nc")
        area = editor.findChild(LineNumberArea)
        blocks = list(area.visible_blocks())
        assert [b.blockNumber() for b, _top, _bottom in blocks] == [0, 1, 2]
        tops = [top for _b, top, _bottom in blocks]
        assert tops == sorted(tops)


class _FixedGutter(GutterWidget):
    WIDTH = 7

    def width_hint(self) -> int:
        return self.WIDTH

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        QtGui.QPainter(self).fillRect(event.rect(), self.bg_color)


class TestGutterLayout:
    def test_gutter_adds_and_removes_itself(self, bare_editor):
        assert list(bare_editor.gutters) == []
        gutter = _FixedGutter(bare_editor)
        assert list(bare_editor.gutters) == [gutter]
        assert gutter.isVisible()
        assert bare_editor.viewportMargins().left() == _FixedGutter.WIDTH
        gutter.remove()
        assert list(bare_editor.gutters) == []
        assert bare_editor.viewportMargins().left() == 0

    def test_width_change_moves_the_gutters_after_it(self, bare_editor):
        first, second = _FixedGutter(bare_editor), _FixedGutter(bare_editor)
        assert second.geometry().left() - first.geometry().left() == 7
        first.WIDTH = 20
        first.update_width()
        assert second.geometry().left() - first.geometry().left() == 20
        assert bare_editor.viewportMargins().left() == 27

    def test_gutters_fill_the_editor_height(self, bare_editor):
        gutter = _FixedGutter(bare_editor)
        bare_editor.resize(bare_editor.width(), bare_editor.height() + 50)
        assert gutter.geometry().height() == bare_editor.contentsRect().height()

    def test_base_class_needs_a_width_and_painting(self, bare_editor):
        with pytest.raises(NotImplementedError):
            GutterWidget(bare_editor)
        assert list(bare_editor.gutters) == []
