#!/bin/bash
VENV_DIR="$HOME/.venvs/spliter3"
VENV_DIR="${VENV_DIR//$'\r'/}"
REQUIREMENTS="/mnt/d/AiChess/spliter3/spliter/requirements.txt"
echo "Creating venv in $VENV_DIR (Linux filesystem)..."
mkdir -p "$HOME/.venvs"
python3 -m venv "$VENV_DIR"
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$REQUIREMENTS"
echo "Done. Run: bash run_spliter.sh --defaults"
