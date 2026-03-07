#!/bin/bash
echo "=== PROGRESS ==="
echo ""
echo "Pip:"
pip3 --version 2>/dev/null || echo "  not installed"
echo ""
echo "Python packages:"
python3 -c "import cv2; print('  cv2 (opencv): OK')" 2>/dev/null || echo "  cv2: not installed"
python3 -c "import numpy; print('  numpy: OK')" 2>/dev/null || echo "  numpy: not installed"
echo ""
echo "Spliter ready:"
cd /mnt/d/AiChess/spliter3/spliter 2>/dev/null && python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from main import main
    print('  Yes - can run main')
except Exception as e:
    print('  No -', str(e)[:60])
" 2>/dev/null || echo "  No - check path"
echo ""
echo "Processes (apt/pip):"
ps aux 2>/dev/null | grep -E ' apt| pip' | grep -v grep || echo "  none"
