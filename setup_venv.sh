#!/bin/bash
SPLITER_DIR="/mnt/d/AiChess/spliter3/spliter"
SPLITER_DIR="${SPLITER_DIR//$'\r'/}"
cd "$SPLITER_DIR" || exit 1
set -e
echo "Creating virtual environment in .venv ..."
python3 -m venv .venv
echo "Installing dependencies ..."
.venv/bin/pip install -r requirements.txt
echo "Done. Run: bash run_spliter.sh --defaults"
