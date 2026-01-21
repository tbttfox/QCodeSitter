#!/usr/bin/env bash
set -e

# Resolve the directory this script lives in
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Pick a Python executable. Default to the py launcher
if command -v py >/dev/null 2>&1; then
    PYTHON="py -3.11"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Error: Python not found on PATH"
    exit 1
fi

activate_venv() {
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        # macOS / Linux
        source "$VENV_DIR/bin/activate"
    elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then
        # Windows (Git Bash / MSYS)
        source "$VENV_DIR/Scripts/activate"
    else
        echo "Error: Could not find virtualenv activate script"
        exit 1
    fi
}

# Create virtual environment if it doesn't exist
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Building Virtualenv..."
    $PYTHON -m venv "$VENV_DIR"

    activate_venv
    # Upgrade pip and install PySide6
    python -m pip install --upgrade pip
    # pip install Qt.py stransi tree-sitter tree-sitter-python PySide6
    pip install PySide6
    pip install -e ${SCRIPT_DIR}
else
    activate_venv
fi

python ${SCRIPT_DIR}/src/QCodeSitter/_kickoff.py
