"""Tests for the TabCompletion behavior, its popup and its providers"""

from __future__ import annotations

import sys

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.behaviors.tab_completion import (
    Completion,
    TabCompletion,
    context_at_cursor,
    identifier_before,
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
        context = context_at_cursor(completion_editor)
        found = {(c.text, c.kind) for c in provider.provide(context)}
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
        context = context_at_cursor(bare_editor)
        assert IdentifierProvider(bare_editor).provide(context) == set()


class TestMainPythonProvider:
    def test_provides_main_namespace(self, editor, monkeypatch):
        main = sys.modules["__main__"]
        monkeypatch.setattr(main, "qcs_test_value", 1, raising=False)
        monkeypatch.setattr(main, "qcs_test_class", int, raising=False)
        monkeypatch.setattr(main, "qcs_test_module", pytest, raising=False)
        editor.setPlainText("qcs_test")
        set_cursor_position(editor, 8)
        provided = MainPythonProvider(editor).provide(context_at_cursor(editor))
        assert {(c.text, c.kind) for c in provided} == {
            ("qcs_test_value", "variable"),
            ("qcs_test_class", "class"),
            ("qcs_test_module", "module"),
        }


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

    def test_tab_accepts_when_added_after_smart_indent(self, qtbot, completion_editor):
        # Like turning completion back on in PrEditor, after the other behaviors
        completion_editor.add_behavior(TabCompletion).add_provider(IdentifierProvider)
        type_text(qtbot, completion_editor, "Calc")
        wait_for_popup(qtbot, completion_editor)
        simulate_keypress(qtbot, completion_editor, KEY.Key_Tab)
        assert completion_editor.toPlainText() == SAMPLE + "Calculator"

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
        completion_editor.get_behavior(TabCompletion).refresh_completions()
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

    def test_identifier_before(self):
        assert identifier_before("x = os.path.jo", 14) == (12, "jo")
        assert identifier_before("x = abc1", 8) == (4, "abc1")

    def test_no_completion_in_the_middle_of_a_word(self, qtbot, completion_editor):
        completion_editor.insertPlainText("Calcx")
        set_cursor_position(completion_editor, len(SAMPLE) + 4)
        completion_editor.get_behavior(TabCompletion).refresh_completions()
        assert not popup(completion_editor).isVisible()

    def test_a_new_word_asks_the_providers_again(self, qtbot, completion_editor):
        """A word typed where an old one was doesn't reuse the old completions"""
        completion = completion_editor.get_behavior(TabCompletion)
        type_text(qtbot, completion_editor, "Calc")
        wait_for_popup(qtbot, completion_editor)
        simulate_keypress(qtbot, completion_editor, KEY.Key_Escape)
        for _ in range(4):
            simulate_keypress(qtbot, completion_editor, KEY.Key_Backspace)
        # Define a new name below, and type the same word in the same place
        end = len(SAMPLE)
        cursor = completion_editor.textCursor()
        cursor.setPosition(end)
        cursor.insertText("\nCalcium = 1")
        set_cursor_position(completion_editor, end)
        type_text(qtbot, completion_editor, "Calc")
        completion.refresh_completions()
        assert shown_texts(completion_editor) == ["Calcium", "Calculator"]

    def test_completes_at_the_start_of_the_document(self, qtbot, completion_editor):
        """Nothing shown yet doesn't count as already completing at line 0"""
        set_cursor_position(completion_editor, 0)
        completion_editor.insertPlainText("\n")
        set_cursor_position(completion_editor, 0)
        type_text(qtbot, completion_editor, "Calc")
        completion_editor.get_behavior(TabCompletion).refresh_completions()
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
            Provider(editor).provide(context_at_cursor(editor))

    def test_context_at_cursor(self, editor):
        editor.setPlainText("x = os.pa")
        set_cursor_position(editor, 9)
        context = context_at_cursor(editor)
        assert (context.line_num, context.index, context.start) == (0, 9, 7)
        assert (context.prefix, context.line) == ("pa", "x = os.pa")
        assert context.node is not None


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
