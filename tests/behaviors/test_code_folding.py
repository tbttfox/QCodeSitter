"""Tests for the CodeFolding behavior"""

from __future__ import annotations

from Qt import QtCore

from QCodeSitter.behaviors.code_folding import (
    CodeFolding,
    FoldableRegion,
)
from tests.helpers import (
    set_cursor_position,
    set_cursor_selection,
)


def _region(folding: CodeFolding, node_type: str, line: int) -> FoldableRegion:
    return next(
        r
        for r in folding.regions
        if r.node is not None and r.node.type == node_type and r.start_line == line
    )


def _hidden_lines(editor) -> list[int]:
    doc = editor.document()
    return [
        i for i in range(doc.blockCount()) if not doc.findBlockByNumber(i).isVisible()
    ]


class TestCodeFolding:
    """Test code folding behavior.

    The sample text has hello() on lines 0-5, and class Greeter on lines 7-12
    with __init__ on lines 8-9 and greet() on lines 11-12
    """

    def test_fold_hides_the_body(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        hello = _region(folding, "function_definition", 0)
        folding.set_folded(hello, True)
        assert _hidden_lines(editor_with_text) == [1, 2, 3, 4, 5]
        folding.set_folded(hello, False)
        assert _hidden_lines(editor_with_text) == []

    def test_bracket_region_keeps_its_last_line(self, editor):
        editor.setPlainText("x = [\n    1,\n    2,\n]\n")
        folding = editor.get_behavior(CodeFolding)
        folding.set_folded(_region(folding, "list", 0), True)
        assert _hidden_lines(editor) == [1, 2]

    def test_unfolding_keeps_nested_folds(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        init = _region(folding, "function_definition", 8)
        greeter = _region(folding, "class_definition", 7)
        folding.set_folded(init, True)
        folding.set_folded(greeter, True)
        assert _hidden_lines(editor_with_text) == [8, 9, 10, 11, 12]
        folding.set_folded(greeter, False)
        assert _hidden_lines(editor_with_text) == [9]

    def test_manual_fold(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        doc = editor_with_text.document()
        set_cursor_selection(
            editor_with_text,
            doc.findBlockByNumber(1).position(),
            doc.findBlockByNumber(4).position(),
        )
        assert folding.create_manual_fold()
        # A manual fold keeps its last line showing
        assert _hidden_lines(editor_with_text) == [2, 3]
        assert any(r.is_manual and r.is_folded for r in folding.regions)

    def test_manual_fold_follows_its_lines(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        doc = editor_with_text.document()
        set_cursor_selection(
            editor_with_text,
            doc.findBlockByNumber(1).position(),
            doc.findBlockByNumber(4).position(),
        )
        folding.create_manual_fold()
        # A new line above the fold moves its lines down
        set_cursor_position(editor_with_text, 0)
        editor_with_text.insert_text("\n")
        assert _hidden_lines(editor_with_text) == [3, 4]
        manual = next(r for r in folding.regions if r.is_manual)
        assert (manual.start_line, manual.end_line) == (2, 5)
        # The gutter toggles the manual fold, not the tree's region on its line
        assert folding.folding_area.region_starts[2] is manual

    def test_manual_fold_needs_two_lines(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        set_cursor_selection(editor_with_text, 0, 3)
        assert not folding.create_manual_fold()
        assert _hidden_lines(editor_with_text) == []

    def test_fold_survives_edit_elsewhere(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        folding.set_folded(_region(folding, "function_definition", 11), True)
        # Edit line 9, which doesn't move greet()
        set_cursor_position(
            editor_with_text,
            editor_with_text.document().findBlockByNumber(9).position(),
        )
        editor_with_text.insert_text("x = 1  # ")
        greet = _region(folding, "function_definition", 11)
        assert greet.is_folded
        assert _hidden_lines(editor_with_text) == [12]

    def test_moved_fold_unfolds(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        folding.set_folded(_region(folding, "function_definition", 11), True)
        # A new line above greet() moves it, so it can't be matched up
        set_cursor_position(editor_with_text, 0)
        editor_with_text.insert_text("\n")
        assert not any(r.is_folded for r in folding.regions)
        assert _hidden_lines(editor_with_text) == []

    def test_remove_shows_every_line(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        folding.fold_all()
        assert _hidden_lines(editor_with_text)
        editor_with_text.remove_behavior(CodeFolding)
        assert _hidden_lines(editor_with_text) == []

    def test_folding_regions_detected(self, editor_with_text):
        editor = editor_with_text
        folding = editor.get_behavior(CodeFolding)
        # The sample code has functions and classes that should be foldable
        regions = {(r.node.type, r.start_line) for r in folding.regions}
        assert ("function_definition", 0) in regions
        assert ("class_definition", 7) in regions

    def test_gutter_click_toggles_the_fold(self, editor_with_text, qtbot):
        folding = editor_with_text.get_behavior(CodeFolding)
        greeter = _region(folding, "class_definition", 7)
        block = editor_with_text.document().findBlockByNumber(7)
        top = editor_with_text.blockBoundingGeometry(block).translated(
            editor_with_text.contentOffset()
        )
        point = QtCore.QPoint(folding.folding_area.width() // 2, int(top.center().y()))
        qtbot.mouseClick(
            folding.folding_area, QtCore.Qt.MouseButton.LeftButton, pos=point
        )
        assert greeter.is_folded
        assert _hidden_lines(editor_with_text) == [8, 9, 10, 11, 12]
        qtbot.mouseClick(
            folding.folding_area, QtCore.Qt.MouseButton.LeftButton, pos=point
        )
        assert not greeter.is_folded

    def test_unfold_to_level(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        folding.fold_all()
        folding.unfold_to_level(0)
        assert all(r.is_folded == (r.depth > 0) for r in folding.regions)
        # Greeter's methods stay folded inside the unfolded class
        assert _hidden_lines(editor_with_text) == [3, 4, 5, 9, 12]

    def test_fold_to_level_shortcut(self, editor_with_text):
        folding = editor_with_text.get_behavior(CodeFolding)
        action = next(
            a for a in folding.shortcut_actions if a.text() == "Fold to Level 1"
        )
        action.trigger()
        regions = folding.regions
        assert all(r.is_folded == (r.depth >= 1) for r in regions)
        assert any(r.is_folded for r in regions)
        assert any(not r.is_folded for r in regions)
