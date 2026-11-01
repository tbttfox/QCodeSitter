"""Tests for the TabCompletion behavior, its popup and its providers"""

from __future__ import annotations

import sys

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.behaviors.tab_completion import (
    Completion,
    TabCompletion,
    merge_completions,
)
from QCodeSitter.behaviors.tab_completion.popup import CompletionPopup
from QCodeSitter.behaviors.tab_completion.providers import (
    IdentifierProvider,
    MainPythonProvider,
)
from QCodeSitter.behaviors.tab_completion.types import Provider
from tests.helpers import set_cursor_position, simulate_keypress

KEY = QtCore.Qt.Key

SAMPLE = """import os
from collections import OrderedDict as odict

def compute(alpha, beta):
    total = alpha + beta
    return total

class Calculator:
    pass

"""


@pytest.fixture
def completion_editor(editor):
    editor.setPlainText(SAMPLE)
    set_cursor_position(editor, len(SAMPLE))
    return editor


def type_text(qtbot, editor, text: str):
    for char in text:
        simulate_keypress(qtbot, editor, KEY.Key_unknown, char)


def popup(editor):
    return editor.get_behavior(TabCompletion).completion_popup


def shown_texts(editor) -> list[str]:
    widget = popup(editor)
    return [
        widget.item(i).data(QtCore.Qt.ItemDataRole.UserRole).text
        for i in range(widget.count())
    ]


def wait_for_popup(qtbot, editor):
    # The debounce timer is 0 in the tests, but still runs from the event loop
    qtbot.waitUntil(lambda: popup(editor).isVisible())


class TestIdentifierProvider:
    def test_provides_document_names(self, completion_editor):
        provider = IdentifierProvider(completion_editor)
        found = {(c.text, c.kind) for c in provider.provide()}
        assert {
            ("os", "import"),
            ("odict", "import"),
            ("compute", "function"),
            ("alpha", "parameter"),
            ("total", "variable"),
            ("Calculator", "class"),
        } <= found

    def test_no_tree(self, bare_editor):
        bare_editor.tree_manager.set_language(None)
        assert IdentifierProvider(bare_editor).provide() == set()


class TestMainPythonProvider:
    def test_provides_main_namespace(self, editor, monkeypatch):
        main = sys.modules["__main__"]
        monkeypatch.setattr(main, "qcs_test_value", 1, raising=False)
        monkeypatch.setattr(main, "qcs_test_class", int, raising=False)
        monkeypatch.setattr(main, "qcs_test_module", pytest, raising=False)
        found = {(c.text, c.kind) for c in MainPythonProvider(editor).provide()}
        assert {
            ("qcs_test_value", "variable"),
            ("qcs_test_class", "class"),
            ("qcs_test_module", "module"),
        } <= found


class TestCompletionPopup:
    def test_typing_shows_matching_completions(self, qtbot, completion_editor):
        type_text(qtbot, completion_editor, "co")
        wait_for_popup(qtbot, completion_editor)
        assert shown_texts(completion_editor) == ["compute"]

    def test_filter_narrows_and_refreshes(self, qtbot, completion_editor):
        type_text(qtbot, completion_editor, "al")
        wait_for_popup(qtbot, completion_editor)
        assert shown_texts(completion_editor) == ["alpha"]

        # A new word asks the providers again, instead of reusing the old items
        simulate_keypress(qtbot, completion_editor, KEY.Key_Escape)
        type_text(qtbot, completion_editor, " Ca")
        wait_for_popup(qtbot, completion_editor)
        assert shown_texts(completion_editor) == ["Calculator"]

    def test_tab_accepts(self, qtbot, completion_editor):
        type_text(qtbot, completion_editor, "Calc")
        wait_for_popup(qtbot, completion_editor)
        simulate_keypress(qtbot, completion_editor, KEY.Key_Tab)
        assert completion_editor.toPlainText() == SAMPLE + "Calculator"
        assert not popup(completion_editor).isVisible()

    def test_navigation_wraps(self, qtbot, completion_editor):
        type_text(qtbot, completion_editor, "o")
        # One letter isn't enough to trigger completion
        assert not popup(completion_editor).isVisible()
        completion_editor.get_behavior(TabCompletion).completion_popup.show_completions(
            [Completion("one", "variable", 1), Completion("other", "variable", 1)], "o"
        )
        simulate_keypress(qtbot, completion_editor, KEY.Key_Up)
        assert popup(completion_editor).currentItem().text() == "other (variable)"
        simulate_keypress(qtbot, completion_editor, KEY.Key_Down)
        simulate_keypress(qtbot, completion_editor, KEY.Key_Return)
        assert completion_editor.toPlainText() == SAMPLE + "one"

    def test_escape_hides_and_consumes(self, qtbot, completion_editor):
        type_text(qtbot, completion_editor, "co")
        wait_for_popup(qtbot, completion_editor)
        simulate_keypress(qtbot, completion_editor, KEY.Key_Escape)
        assert not popup(completion_editor).isVisible()
        assert completion_editor.toPlainText() == SAMPLE + "co"

    def test_backspace_hides_and_deletes(self, qtbot, completion_editor):
        type_text(qtbot, completion_editor, "co")
        wait_for_popup(qtbot, completion_editor)
        simulate_keypress(qtbot, completion_editor, KEY.Key_Backspace)
        assert not popup(completion_editor).isVisible()
        assert completion_editor.toPlainText() == SAMPLE + "c"

    def test_tab_indents_without_popup(self, qtbot, completion_editor):
        simulate_keypress(qtbot, completion_editor, KEY.Key_Tab)
        assert completion_editor.toPlainText() == SAMPLE + "    "

    def test_no_completion_in_strings(self, qtbot, completion_editor):
        type_text(qtbot, completion_editor, 'x = "co')
        # Run the debounced completion now, instead of waiting for the timer
        completion_editor.get_behavior(TabCompletion).do_completion()
        assert not popup(completion_editor).isVisible()

    def test_vim_keys(self, qtbot, completion_editor):
        completion_editor.options["vim_completion_keys"] = True
        type_text(qtbot, completion_editor, "Calc")
        wait_for_popup(qtbot, completion_editor)
        simulate_keypress(
            qtbot,
            completion_editor,
            KEY.Key_Y,
            modifiers=QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        assert completion_editor.toPlainText() == SAMPLE + "Calculator"

    def test_extract_prefix_stops_at_dot(self):
        assert TabCompletion._extract_prefix("x = os.path.jo", 14) == (12, "jo")

    def test_completes_at_the_start_of_the_document(self, qtbot, completion_editor):
        """Nothing shown yet doesn't count as already completing at line 0"""
        set_cursor_position(completion_editor, 0)
        type_text(qtbot, completion_editor, "Calc")
        completion_editor.get_behavior(TabCompletion).do_completion()
        assert shown_texts(completion_editor) == ["Calculator"]

    def test_popup_follows_the_colors_option(self, completion_editor):
        completion_editor.options["colors"] = {"menu": "#010203"}
        palette = popup(completion_editor).palette()
        assert palette.color(QtGui.QPalette.ColorRole.Base) == QtGui.QColor("#010203")


class TestCompletionTypes:
    def test_completion(self):
        comp = Completion("path", "module", 2)
        assert comp.display() == "path (module)"
        # The same name and kind is one completion, whatever the priority
        assert comp == Completion("path", "module", 5)
        assert hash(comp) == hash(Completion("path", "module", 5))
        assert comp != Completion("path", "variable", 2)

    def test_merge_keeps_the_highest_priority(self):
        merged = merge_completions(
            [
                Completion("path", "module", 2),
                Completion("path", "module", 5),
                Completion("path", "module", 1),
                Completion("path", "variable", 1),
            ]
        )
        assert {(c.text, c.kind, c.priority) for c in merged} == {
            ("path", "module", 5),
            ("path", "variable", 1),
        }

    def test_provider_base(self, editor):
        with pytest.raises(NotImplementedError):
            Provider(editor).provide()

    def test_providers_take_the_editor(self, editor):
        editor.setPlainText("def foo(): pass")
        assert Completion("foo", "function", 3) in IdentifierProvider(editor).provide()
        assert all(
            isinstance(c, Completion) for c in MainPythonProvider(editor).provide()
        )


class TestCompletionPopupWidget:
    def test_filter_and_accept(self, editor):
        editor.setPlainText("pr")
        cursor = editor.textCursor()
        cursor.setPosition(2)
        editor.setTextCursor(cursor)
        popup = CompletionPopup(editor)
        popup.show_completions(
            [
                Completion("print", "function", 1),
                Completion("property", "class", 2),
                Completion("pr", "variable", 9),
            ],
            "pr",
        )
        # Sorted by priority, and the prefix itself isn't offered
        assert [popup.item(i).text() for i in range(popup.count())] == [
            "property (class)",
            "print (function)",
        ]
        popup.update_filter("pri")
        assert popup.count() == 1
        popup.accept_completion()
        assert editor.toPlainText() == "print"
        assert not popup.isVisible()
        popup.deleteLater()

    def test_no_matches_hides(self, editor):
        popup = CompletionPopup(editor)
        popup.show_completions([Completion("print", "function", 1)], "xy")
        assert popup.count() == 0
        assert not popup.isVisible()
        popup.deleteLater()
