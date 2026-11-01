"""Tests that the example scripts run"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from QCodeSitter.defaults import (
    DEFAULT_BEHAVIORS,
    OPTIONAL_BEHAVIORS,
)


class TestDemo:
    def test_build_window(self, qtbot):
        path = Path(__file__).parents[2] / "examples" / "demo.py"
        spec = importlib.util.spec_from_file_location("qcodesitter_demo", path)
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)

        win = demo.build_window()
        qtbot.addWidget(win)
        editor = win.centralWidget()
        assert isinstance(editor, demo.CodeEditor)
        for behavior_cls in DEFAULT_BEHAVIORS + OPTIONAL_BEHAVIORS:
            assert editor.get_behavior(behavior_cls) is not None
