"""
The advertised keyboard shortcuts fire their actions when pressed in the editor
"""

from __future__ import annotations

import pytest
from Qt import QtGui
from Qt.QtTest import QTest

ADVERTISED = [
    "Ctrl+D",
    "Ctrl+Alt+Up",
    "Ctrl+Alt+Down",
    "Ctrl+Shift+L",
    "Ctrl+/",
    "Ctrl+Shift+[",
    "Ctrl+Shift+]",
    "Ctrl+Shift+.",
    *(f"Ctrl+{i}" for i in range(10)),
]


@pytest.fixture
def active_editor(qtbot, editor):
    editor.activateWindow()
    editor.setFocus()
    qtbot.waitUntil(editor.hasFocus)
    return editor


def actions_for(editor, sequence):
    want = QtGui.QKeySequence(sequence)
    return [a for a in editor.actions() if a.shortcut() == want]


@pytest.mark.parametrize("sequence", ADVERTISED)
def test_shortcut_is_bound_once(editor, sequence):
    assert len(actions_for(editor, sequence)) == 1


@pytest.mark.parametrize("sequence", ADVERTISED)
def test_pressing_shortcut_triggers_action(active_editor, sequence):
    (action,) = actions_for(active_editor, sequence)
    fired = []
    action.triggered.connect(lambda *_args: fired.append(True))
    QTest.keySequence(active_editor, QtGui.QKeySequence(sequence))
    assert fired == [True]


def test_ctrl_slash_comments_the_line(active_editor):
    active_editor.setPlainText("x = 1")
    QTest.keySequence(active_editor, QtGui.QKeySequence("Ctrl+/"))
    assert active_editor.toPlainText() == "# x = 1"


def test_ctrl_alt_down_adds_a_cursor(active_editor):
    active_editor.setPlainText("a\nb")
    QTest.keySequence(active_editor, QtGui.QKeySequence("Ctrl+Alt+Down"))
    cursors, _ = active_editor.cursors.in_document_order()
    assert len(cursors) == 2
