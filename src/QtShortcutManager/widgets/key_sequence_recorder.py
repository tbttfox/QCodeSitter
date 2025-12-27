from __future__ import annotations
from typing import Optional

from Qt import QtCompat
from Qt.QtCore import Qt, QTimer
from Qt.QtGui import QKeySequence
from Qt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
    QFrame,
)


class KeySequenceRecorderDialog(QDialog):
    """Dialog for recording keyboard shortcut sequences.

    Supports multi-combination sequences like Ctrl+K, Ctrl+C (up to 4 combinations).
    Uses a timeout-based approach to detect when the user has finished entering
    a sequence.
    """

    def __init__(self, parent=None, existing_sequence: Optional[QKeySequence] = None):
        super().__init__(parent)
        self.setWindowTitle("Record Shortcut")
        self.setModal(True)

        self._recording = False
        self._key_presses: list[int] = []
        self._recorded_sequence: Optional[QKeySequence] = None
        self._max_combinations = 4  # Qt supports up to 4 key combinations

        # Timer for detecting end of sequence input
        self._record_timer = QTimer(self)
        self._record_timer.setSingleShot(True)
        self._record_timer.setInterval(800)  # 800ms timeout
        self._record_timer.timeout.connect(self._on_record_timeout)

        self._setup_ui()

        # If editing existing sequence, show it
        if existing_sequence:
            self._display.setText(existing_sequence.toString(QKeySequence.NativeText))
            self._recorded_sequence = existing_sequence

    def _setup_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "Press the key combination you want to assign.\n"
            "For multi-key sequences (like Ctrl+K, Ctrl+C), press combinations in sequence.\n"
            "Press Escape to cancel."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        layout.addSpacing(10)

        # Display frame for recorded sequence
        display_frame = QFrame()
        display_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        display_layout = QVBoxLayout(display_frame)

        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setPlaceholderText("Press keys to record...")
        self._display.setMinimumWidth(300)
        self._display.setAlignment(Qt.AlignCenter)

        # Make display text larger
        font = self._display.font()
        font.setPointSize(font.pointSize() + 2)
        self._display.setFont(font)

        display_layout.addWidget(self._display)
        layout.addWidget(display_frame)

        layout.addSpacing(10)

        # Control buttons
        button_layout = QHBoxLayout()

        self._record_button = QPushButton("Start Recording")
        self._record_button.setCheckable(True)
        self._record_button.clicked.connect(self._toggle_recording)
        button_layout.addWidget(self._record_button)

        self._clear_button = QPushButton("Clear")
        self._clear_button.clicked.connect(self._clear_sequence)
        button_layout.addWidget(self._clear_button)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        layout.addSpacing(10)

        # OK/Cancel buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        # Start recording automatically
        QTimer.singleShot(100, lambda: self._toggle_recording(True))

    def _toggle_recording(self, checked: bool):
        """Toggle recording mode on/off."""
        self._recording = checked

        if checked:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Enter recording mode."""
        self._key_presses.clear()
        self._display.setText("")
        self._display.setPlaceholderText("Recording... (Press Escape to cancel)")
        self._record_button.setText("Stop Recording")
        self._record_button.setChecked(True)
        self.setFocus()

    def _stop_recording(self):
        """Exit recording mode."""
        self._recording = False
        self._record_timer.stop()
        self._record_button.setText("Start Recording")
        self._record_button.setChecked(False)

        if self._key_presses:
            self._finalize_sequence()

    def _clear_sequence(self):
        """Clear the recorded sequence."""
        self._key_presses.clear()
        self._recorded_sequence = None
        self._display.clear()
        self._display.setPlaceholderText("Press keys to record...")
        self._record_timer.stop()

    def _finalize_sequence(self):
        """Create final QKeySequence from recorded key presses."""
        if not self._key_presses:
            return

        # Qt's QKeySequence constructor takes up to 4 key combinations
        # Pad with 0s if less than 4, or take only first 4
        keys = (self._key_presses + [0, 0, 0, 0])[:4]
        self._recorded_sequence = QKeySequence(keys[0], keys[1], keys[2], keys[3])

        # Update display
        self._display.setText(self._recorded_sequence.toString(QKeySequence.NativeText))

    def _on_record_timeout(self):
        """Called when timer expires - finalize the sequence."""
        if self._recording and self._key_presses:
            self._stop_recording()

    def keyPressEvent(self, event):
        """Capture key press events during recording."""
        if not self._recording:
            return super().keyPressEvent(event)

        key = event.key()

        # Handle Escape to cancel
        if key == Qt.Key_Escape:
            self._cancel_recording()
            return

        # Ignore modifier-only presses
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        # Build key combination: modifiers + key
        modifiers = QtCompat.enumValue(event.modifiers())

        # Filter out numpad key modifier on Windows
        # (Qt.KeypadModifier is often set automatically)
        modifiers &= ~QtCompat.enumValue(Qt.KeypadModifier)

        key_combo = key | modifiers

        # Add to sequence
        if len(self._key_presses) < self._max_combinations:
            self._key_presses.append(key_combo)

            # Show live preview (pad with 0s to make 4 keys)
            keys = (self._key_presses + [0, 0, 0, 0])[:4]
            temp_seq = QKeySequence(keys[0], keys[1], keys[2], keys[3])
            self._display.setText(temp_seq.toString(QKeySequence.NativeText))

            # Restart timeout timer
            self._record_timer.start()
        else:
            # Reached maximum combinations, finalize immediately
            self._stop_recording()

    def _cancel_recording(self):
        """Cancel recording and clear any partial input."""
        self._key_presses.clear()
        self._stop_recording()
        if not self._recorded_sequence:
            self._display.clear()
            self._display.setPlaceholderText("Press keys to record...")

    def get_key_sequence(self) -> Optional[QKeySequence]:
        """Get the recorded key sequence.

        Returns:
            The recorded QKeySequence, or None if no sequence was recorded
        """
        return self._recorded_sequence

    @staticmethod
    def record_sequence(
        parent=None, existing_sequence: Optional[QKeySequence] = None
    ) -> Optional[QKeySequence]:
        """Static convenience method to show dialog and get a key sequence.

        Args:
            parent: Parent widget
            existing_sequence: Optional existing sequence to edit

        Returns:
            Recorded QKeySequence, or None if canceled
        """
        dialog = KeySequenceRecorderDialog(parent, existing_sequence)
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_key_sequence()
        return None
