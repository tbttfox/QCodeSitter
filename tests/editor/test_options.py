"""Tests for the editor options, and how behaviors watch them"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.behaviors import Behavior
from QCodeSitter.defaults import (
    DEFAULT_BEHAVIORS,
    OPTIONAL_BEHAVIORS,
    default_options,
    install_default_behaviors,
)
from QCodeSitter.editor_options import OPTION_DEFAULTS, OPTION_KEYS, EditorOptions
from QCodeSitter.highlighting.themes import LIGHT_THEME, read_theme


class TestEditorOptions:
    def test_unknown_key_raises(self, qapp):
        with pytest.raises(KeyError):
            EditorOptions({"not_an_option": 1})
        options = EditorOptions()
        with pytest.raises(KeyError):
            options["indent_with_tabs"] = True
        with pytest.raises(KeyError):
            options.update({"colour": {}})

    def test_wrong_type_raises(self, qapp):
        with pytest.raises(TypeError, match="space_indent_width"):
            EditorOptions({"space_indent_width": "4"})
        options = EditorOptions()
        with pytest.raises(TypeError):
            options["indent_using_tabs"] = 1
        with pytest.raises(TypeError):
            options.update({"font": "Consolas"})
        # A failed update changes nothing
        assert options["indent_using_tabs"] is False

    def test_unset_options_have_defaults(self, qapp):
        options = EditorOptions()
        for key, value in OPTION_DEFAULTS.items():
            assert options[key] == value
        assert "language" not in options
        assert "font" not in options

    def test_defaults_are_not_shared(self, qapp):
        first, second = EditorOptions(), EditorOptions()
        first["indent_bracket_pairs"].append("<>")
        assert second["indent_bracket_pairs"] == OPTION_DEFAULTS["indent_bracket_pairs"]

    def test_update_emits_keys(self, qapp):
        options = EditorOptions()
        emitted = []
        options.optionsUpdated.connect(emitted.append)
        options.update({"space_indent_width": 2, "indent_using_tabs": True})
        options["debounce_delay"] = 5
        assert emitted == [
            ["space_indent_width", "indent_using_tabs"],
            ["debounce_delay"],
        ]

    def test_apply_only_set_keys(self, qapp):
        options = EditorOptions({"space_indent_width": 2})
        seen = {}
        handlers = {
            k: (lambda v, k=k: seen.__setitem__(k, v))
            for k in ("space_indent_width", "font")
        }
        options.apply(handlers, ["space_indent_width", "font"])
        assert seen == {"space_indent_width": 2}


class _RecordingBehavior(Behavior):
    def __init__(self, editor):
        super().__init__(editor)
        self.widths = []
        self.watch_options({"space_indent_width": self.widths.append})
        self.apply_all_options()


class TestBehaviorBase:
    def test_watch_options(self, editor):
        behavior = editor.add_behavior(_RecordingBehavior)
        assert behavior.widths == [4]
        editor.options["space_indent_width"] = 2
        assert behavior.widths == [4, 2]
        editor.remove_behavior(_RecordingBehavior)
        editor.options["space_indent_width"] = 8
        assert behavior.widths == [4, 2]

    def test_watch_unknown_option_raises(self, editor):
        behavior = editor.add_behavior(_RecordingBehavior)
        with pytest.raises(KeyError):
            behavior.watch_options({"space_indent": print})

    def test_key_press_not_implemented(self, editor):
        with pytest.raises(NotImplementedError):
            Behavior(editor).handle_key_press(
                QtGui.QKeyEvent(
                    QtCore.QEvent.Type.KeyPress,
                    QtCore.Qt.Key.Key_A,
                    QtCore.Qt.KeyboardModifier.NoModifier,
                )
            )


class TestDefaults:
    def test_default_options(self, qapp, python_language):
        options = default_options(LIGHT_THEME, python_language)
        assert set(options.keys()) <= OPTION_KEYS
        colors, syntax = read_theme(LIGHT_THEME)
        assert options["colors"] == colors
        assert options["syntax"] == syntax
        assert options["language"] == python_language

    def test_install_default_behaviors(self, bare_editor):
        install_default_behaviors(bare_editor)
        for behavior_cls in DEFAULT_BEHAVIORS:
            assert bare_editor.get_behavior(behavior_cls) is not None
        for behavior_cls in OPTIONAL_BEHAVIORS:
            assert bare_editor.get_behavior(behavior_cls) is None
