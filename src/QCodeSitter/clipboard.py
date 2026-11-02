"""The clipboard format for text copied from several cursors

The texts are joined with newlines as plain text, and their lengths are stored
alongside. Pasting with the same number of cursors gives each cursor its own text.
"""

from __future__ import annotations

import re

from Qt import QtCore

from .constants import MIME


def tabs_to_spaces(text: str, width: int) -> str:
    """Replace the tabs in the indent of each line with spaces"""
    spaces = " " * width
    return re.sub(r"(?m)^\t+", lambda m: spaces * len(m.group()), text)


def encode_multi_copy(texts: list[str]) -> QtCore.QMimeData:
    mime_data = QtCore.QMimeData()
    mime_data.setData(MIME, ",".join(str(len(t)) for t in texts).encode())
    mime_data.setText("\n".join(texts))
    return mime_data


def split_multi_copy(source: QtCore.QMimeData, cursor_count: int) -> list[str] | None:
    """Split the text copied from cursor_count cursors back into its parts

    Returns None if the text wasn't copied from that many cursors, or if
    another program put lengths in our format that can't be read
    """
    if not source.hasFormat(MIME):
        return None
    try:
        lens = [int(n) for n in bytes(source.data(MIME)).decode().split(",")]
    except (UnicodeDecodeError, ValueError):
        return None
    text = source.text()
    newline_separators = len(lens) - 1
    if len(lens) != cursor_count or len(text) != sum(lens) + newline_separators:
        return None
    parts = []
    ptr = 0
    for length in lens:
        parts.append(text[ptr : ptr + length])
        ptr += length + 1
    return parts
