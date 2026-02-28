"""
Fuzz tests for QCodeSitter using Hypothesis.

These tests generate random sequences of editor operations to find
hangs, crashes, and invariant violations. Run with:

    tox -e fuzz
    pytest tests/test_fuzz.py -x --timeout=10
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from Qt import QtCore, QtGui

from QCodeSitter.code_editor import CodeEditor, CursorState
from QCodeSitter.editor_options import EditorOptions

from tests.helpers import simulate_keypress


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
                "set_plain_text",
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

    if kind == "set_plain_text":
        return ("set_plain_text", draw(text_strategy))

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

    elif kind == "set_plain_text":
        editor.setPlainText(op[1])

    elif kind == "set_cursor":
        pos = min(op[1], len(editor.toPlainText()))
        cursor = editor.textCursor()
        cursor.setPosition(pos)
        editor.setTextCursor(cursor)

    elif kind == "add_secondary_cursor":
        pos = min(op[1], len(editor.toPlainText()))
        editor.add_cursor_at_position(pos)

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
        editor.add_next_occurrence()

    elif kind == "add_cursor_above":
        editor.add_cursor_above()

    elif kind == "add_cursor_below":
        editor.add_cursor_below()

    elif kind == "move_cursors":
        _, direction, select, word_mode = op
        editor.move_cursors(direction, select, word_mode)


def reset_editor(editor):
    """Reset editor to a clean state between Hypothesis examples.

    Hypothesis reuses the same fixture across all examples, so we must
    clear mutable state at the start of each example to avoid leakage.
    """
    editor.setPlainText("")
    editor.document().clearUndoRedoStacks()


def check_invariants(editor):
    """Verify editor invariants that must always hold."""
    doc_len = len(editor.toPlainText())

    # Primary cursor must be within document bounds
    cursor = editor.textCursor()
    assert 0 <= cursor.position() <= doc_len, (
        f"Primary cursor position {cursor.position()} out of bounds (doc_len={doc_len})"
    )
    assert 0 <= cursor.anchor() <= doc_len, (
        f"Primary cursor anchor {cursor.anchor()} out of bounds (doc_len={doc_len})"
    )

    # All secondary cursors must be within document bounds
    for i, sc in enumerate(editor.secondary_cursors):
        assert 0 <= sc.position <= doc_len, (
            f"Secondary cursor {i} position {sc.position} out of bounds (doc_len={doc_len})"
        )
        assert 0 <= sc.anchor <= doc_len, (
            f"Secondary cursor {i} anchor {sc.anchor} out of bounds (doc_len={doc_len})"
        )



# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.fuzz
class TestFuzz:
    """Fuzz tests — only run under the 'fuzz' tox env or via -m fuzz."""

    @given(ops=st.lists(operation(), min_size=1, max_size=80))
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_random_operations_bare(self, bare_editor, ops):
        """Random operations on a bare editor (no behaviors) should not crash."""
        reset_editor(bare_editor)
        for op in ops:
            apply_operation(bare_editor, op)
        check_invariants(bare_editor)

    @given(ops=st.lists(operation(), min_size=1, max_size=80))
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_random_operations_full(self, editor, ops):
        """Random operations on a fully-loaded editor should not crash."""
        reset_editor(editor)
        for op in ops:
            apply_operation(editor, op)
        check_invariants(editor)

    @given(
        initial_text=text_strategy,
        ops=st.lists(operation(), min_size=1, max_size=80),
    )
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_random_operations_with_initial_text(self, editor, initial_text, ops):
        """Random operations starting from random initial text should not crash."""
        reset_editor(editor)
        editor.setPlainText(initial_text)
        for op in ops:
            apply_operation(editor, op)
        check_invariants(editor)

    @given(
        n_cursors=st.integers(min_value=2, max_value=20),
        ops=st.lists(operation(), min_size=1, max_size=40),
    )
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_multicursor_stress(self, editor, n_cursors, ops):
        """Multi-cursor editing under stress should not crash."""
        reset_editor(editor)
        # Set up some text to work with
        editor.setPlainText("line one\nline two\nline three\nline four\nline five\n")

        # Add several cursors
        doc_len = len(editor.toPlainText())
        if doc_len > 0:
            step = max(1, doc_len // n_cursors)
            for i in range(1, n_cursors):
                pos = min(i * step, doc_len)
                editor.add_cursor_at_position(pos)

        for op in ops:
            apply_operation(editor, op)
        check_invariants(editor)

    @given(ops=st.lists(st.sampled_from(["undo", "redo"]), min_size=1, max_size=50))
    @settings(
        max_examples=200,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_undo_redo_stress(self, editor, ops):
        """Rapid undo/redo should not crash or corrupt state."""
        reset_editor(editor)
        # Build up some undo history
        editor.insert_text("hello world\n")
        editor.insert_text("foo bar baz\n")
        editor.backspace()
        editor.insert_text("end")

        for op_name in ops:
            if op_name == "undo":
                editor.undo()
            else:
                editor.redo()
        check_invariants(editor)
