"""
Check extracted frames for corruption (same logic as monorepo's _is_frame_corrupted).
"""
import cv2
import numpy as np
import os
import glob

def check_frame(path):
    img = cv2.imread(path)
    if img is None:
        return "UNREADABLE"
    h, w = img.shape[:2]
    
    # Check green channel dominance (green frame artifact)
    b, g, r = cv2.split(img)
    mean_b, mean_g, mean_r = float(np.mean(b)), float(np.mean(g)), float(np.mean(r))
    if mean_g > mean_b * 2 and mean_g > mean_r * 2:
        return f"GREEN FRAME (b={mean_b:.0f} g={mean_g:.0f} r={mean_r:.0f})"
    
    # Check gray (all channels equal, no dark pixels)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    std = float(np.std(gray))
    p5 = float(np.percentile(gray, 5))
    if std < 12:
        return f"BLANK/FLAT (std={std:.1f})"
    if abs(mean_b - mean_g) < 5 and abs(mean_g - mean_r) < 5 and p5 > 65:
        return f"GRAY FILL (p5={p5:.0f} std={std:.1f})"
    
    return f"OK ({w}x{h} b={mean_b:.0f} g={mean_g:.0f} r={mean_r:.0f} std={std:.1f})"

out_root = r'D:\AiChess\spliter3\spliter\videos_out'
jpgs = sorted(glob.glob(out_root + r'\*\jpeg\*.jpg'))

print(f"Checking {len(jpgs)} frames:\n")
for jpg in jpgs:
    parts = jpg.replace(out_root + '\\', '').split('\\')
    label = f"{parts[0]}/{parts[-1]}" if len(parts) >= 3 else jpg
    result = check_frame(jpg)
    icon = "OK" if result.startswith("OK") else "!!"
    print(f"  {icon} {label:55s} {result}")
