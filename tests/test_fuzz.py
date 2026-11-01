"""
Fuzz tests for QCodeSitter using Hypothesis.

These tests generate random sequences of editor operations to find
hangs, crashes, and invariant violations. Run with:

    tox -e fuzz
    pytest tests/test_fuzz.py -x --timeout=10
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from Qt import QtCore, QtWidgets

from QCodeSitter import CodeEditor, EditorOptions
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.utils import MO, len16
from tests.conftest import install_test_behaviors, make_test_options
from tests.helpers import (
    assert_matches_full_highlight,
    assert_tree_matches_fresh_parse,
    simulate_keypress,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Printable text that includes unicode edge-cases
text_strategy = st.text(
    st.sampled_from(
        # ASCII basics
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        # Bracket/quote pairs the editor cares about
        "()[]{}\"'`"
        # Whitespace
        " \t\n"
        # Python operators / punctuation
        "+-*/%=<>!&|^~@:;.,#\\"
        # Non-ASCII / multi-byte
        "\u00e9\u00f1\u00fc"  # accented latin
        "\u4e16\u754c"  # CJK
        "\U0001f600"  # emoji (surrogate pair in UTF-16)
    ),
    min_size=0,
    max_size=50,
)

keys_with_text = [
    (QtCore.Qt.Key.Key_A, "a"),
    (QtCore.Qt.Key.Key_B, "b"),
    (QtCore.Qt.Key.Key_Z, "z"),
    (QtCore.Qt.Key.Key_1, "1"),
    (QtCore.Qt.Key.Key_ParenLeft, "("),
    (QtCore.Qt.Key.Key_ParenRight, ")"),
    (QtCore.Qt.Key.Key_BracketLeft, "["),
    (QtCore.Qt.Key.Key_BracketRight, "]"),
    (QtCore.Qt.Key.Key_BraceLeft, "{"),
    (QtCore.Qt.Key.Key_BraceRight, "}"),
    (QtCore.Qt.Key.Key_QuoteDbl, '"'),
    (QtCore.Qt.Key.Key_Apostrophe, "'"),
    (QtCore.Qt.Key.Key_Space, " "),
    (QtCore.Qt.Key.Key_Tab, ""),
    (QtCore.Qt.Key.Key_Return, ""),
    (QtCore.Qt.Key.Key_Backspace, ""),
    (QtCore.Qt.Key.Key_Delete, ""),
    (QtCore.Qt.Key.Key_Escape, ""),
    (QtCore.Qt.Key.Key_Left, ""),
    (QtCore.Qt.Key.Key_Right, ""),
    (QtCore.Qt.Key.Key_Up, ""),
    (QtCore.Qt.Key.Key_Down, ""),
    (QtCore.Qt.Key.Key_Home, ""),
    (QtCore.Qt.Key.Key_End, ""),
]

modifier_flags = [
    QtCore.Qt.KeyboardModifier.NoModifier,
    QtCore.Qt.KeyboardModifier.ShiftModifier,
    QtCore.Qt.KeyboardModifier.ControlModifier,
    QtCore.Qt.KeyboardModifier.ControlModifier
    | QtCore.Qt.KeyboardModifier.ShiftModifier,
]

keypress_strategy = st.tuples(
    st.sampled_from(keys_with_text),
    st.sampled_from(modifier_flags),
)


# An "operation" is one of several things the fuzzer can do to the editor.
@st.composite
def operation(draw):
    """Draw a single editor operation."""
    kind = draw(
        st.sampled_from(
            [
                "keypress",
                "insert_text",
                "set_cursor",
                "add_secondary_cursor",
                "undo",
                "redo",
                "copy_paste",
                "cut_paste",
                "select_next_occurrence",
                "add_cursor_above",
                "add_cursor_below",
                "move_cursors",
            ]
        )
    )

    if kind == "keypress":
        (key, text), mod = draw(keypress_strategy)
        return ("keypress", key, text, mod)

    if kind == "insert_text":
        return ("insert_text", draw(text_strategy))

    if kind == "set_cursor":
        return ("set_cursor", draw(st.integers(min_value=0, max_value=5000)))

    if kind == "add_secondary_cursor":
        return ("add_secondary_cursor", draw(st.integers(min_value=0, max_value=5000)))

    if kind == "undo":
        return ("undo",)

    if kind == "redo":
        return ("redo",)

    if kind == "copy_paste":
        return ("copy_paste",)

    if kind == "cut_paste":
        return ("cut_paste",)

    if kind == "select_next_occurrence":
        return ("select_next_occurrence",)

    if kind == "add_cursor_above":
        return ("add_cursor_above",)

    if kind == "add_cursor_below":
        return ("add_cursor_below",)

    if kind == "move_cursors":
        direction = draw(
            st.sampled_from(
                [
                    QtCore.Qt.Key.Key_Left,
                    QtCore.Qt.Key.Key_Right,
                    QtCore.Qt.Key.Key_Up,
                    QtCore.Qt.Key.Key_Down,
                    QtCore.Qt.Key.Key_Home,
                    QtCore.Qt.Key.Key_End,
                ]
            )
        )
        select = draw(st.booleans())
        word_mode = draw(st.booleans())
        return ("move_cursors", direction, select, word_mode)


def apply_operation(editor, op):
    """Apply a single fuzz operation to the editor."""
    kind = op[0]

    if kind == "keypress":
        _, key, text, mod = op
        simulate_keypress(None, editor, key, text, mod)

    elif kind == "insert_text":
        editor.insert_text(op[1])

    elif kind == "set_cursor":
        pos = min(op[1], len16(editor.toPlainText()))
        cursor = editor.textCursor()
        cursor.setPosition(pos)
        editor.setTextCursor(cursor)

    elif kind == "add_secondary_cursor":
        pos = min(op[1], len16(editor.toPlainText()))
        editor.cursors.add_at(pos)

    elif kind == "undo":
        editor.undo()

    elif kind == "redo":
        editor.redo()

    elif kind == "copy_paste":
        editor.copy()
        editor.paste()

    elif kind == "cut_paste":
        editor.cut()
        editor.paste()

    elif kind == "select_next_occurrence":
        editor.cursors.add_next_occurrence()

    elif kind == "add_cursor_above":
        editor.cursors.add_above()

    elif kind == "add_cursor_below":
        editor.cursors.add_below()

    elif kind == "move_cursors":
        _, direction, select, word_mode = op
        editor.cursors.move(direction, select, word_mode)


@contextmanager
def fuzz_editor(python_language, full: bool):
    """A fresh shown editor with its own options, closed and deleted afterwards

    Hypothesis runs many examples in one test, so editors must not pile up
    """
    if full:
        editor = CodeEditor(make_test_options(python_language))
        install_test_behaviors(editor)
    else:
        editor = CodeEditor(EditorOptions({"language": python_language}))
    editor.show()
    try:
        yield editor
    finally:
        editor.close()
        editor.deleteLater()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)


def check_invariants(editor):
    """Verify editor invariants that must always hold."""
    # Let any reparse scheduled by an undo or redo run
    QtWidgets.QApplication.processEvents()
    doc_len = len16(editor.toPlainText())

    cursor = editor.textCursor()
    for name, state in [("primary", cursor), *enumerate(editor.cursors.secondary)]:
        position = state.position() if name == "primary" else state.position
        anchor = state.anchor() if name == "primary" else state.anchor
        assert 0 <= position <= doc_len, (
            f"cursor {name} position {position} > {doc_len}"
        )
        assert 0 <= anchor <= doc_len, f"cursor {name} anchor {anchor} > {doc_len}"

    # The incremental tree and highlighting match doing them from scratch
    assert_tree_matches_fresh_parse(editor)
    if editor.get_behavior(SyntaxHighlighting) is not None:
        assert_matches_full_highlight(editor)


FUZZ_SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.fuzz
class TestFuzz:
    """Fuzz tests — only run under the 'fuzz' tox env or via -m fuzz."""

    @given(ops=st.lists(operation(), min_size=1, max_size=80))
    @FUZZ_SETTINGS
    def test_random_operations_bare(self, qapp, python_language, ops):
        """Random operations on a bare editor (no behaviors) should not crash."""
        with fuzz_editor(python_language, full=False) as editor:
            for op in ops:
                apply_operation(editor, op)
            check_invariants(editor)

    @given(ops=st.lists(operation(), min_size=1, max_size=80))
    @FUZZ_SETTINGS
    def test_random_operations_full(self, qapp, python_language, ops):
        """Random operations on a fully-loaded editor should not crash."""
        with fuzz_editor(python_language, full=True) as editor:
            for op in ops:
                apply_operation(editor, op)
            check_invariants(editor)

    @given(
        n_cursors=st.integers(min_value=2, max_value=20),
        ops=st.lists(operation(), min_size=1, max_size=40),
    )
    @FUZZ_SETTINGS
    def test_multicursor_stress(self, qapp, python_language, n_cursors, ops):
        """Multi-cursor editing under stress should not crash."""
        with fuzz_editor(python_language, full=True) as editor:
            editor.insert_text("line one\nline two\nline three\nline four\nline five\n")
            doc_len = len16(editor.toPlainText())
            step = max(1, doc_len // n_cursors)
            for i in range(1, n_cursors):
                editor.cursors.add_at(min(i * step, doc_len))

            for op in ops:
                apply_operation(editor, op)
            check_invariants(editor)

    @given(ops=st.lists(st.sampled_from(["undo", "redo"]), min_size=1, max_size=50))
    @FUZZ_SETTINGS
    def test_undo_redo_stress(self, qapp, python_language, ops):
        """Rapid undo/redo should not crash or corrupt state."""
        with fuzz_editor(python_language, full=True) as editor:
            # Build up some undo history
            editor.insert_text("hello world\n")
            editor.insert_text("foo bar baz\n")
            editor.delete(MO.PreviousCharacter)
            editor.insert_text("end")

            for op_name in ops:
                if op_name == "undo":
                    editor.undo()
                else:
                    editor.redo()
            check_invariants(editor)
