#!/bin/bash
VENV_DIR="$HOME/.venvs/spliter3"
VENV_DIR="${VENV_DIR//$'\r'/}"
SPLITER_DIR="/mnt/d/AiChess/spliter3/spliter"
if [ ! -d "$VENV_DIR" ]; then
  echo "Run first: bash setup_venv_linux_home.sh"
  exit 1
fi
cd "$SPLITER_DIR" || exit 1
"$VENV_DIR/bin/python" main.py "$@"
