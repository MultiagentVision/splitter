"""
Local test runner: process specific videos, output to given folder.
Run as: python run_local_test.py
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(__file__))

from config_utils import load_config
from pipeline import run_pipeline


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    config = load_config(os.path.join(os.path.dirname(__file__), "config.json"))

    config["use_video_files"] = True
    config["use_stream"] = False
    config["frame_mode"] = "rare"
    config["quality_level"] = "medium"
    config["gdrive_links"] = []
    config["max_videos_per_run"] = 0
    config["processes"] = 1

    input_dir = r"D:\AiChess\spliter3\spliter\videos\2904\2905slom_broke"
    output_dir = r"D:\AiChess\spliter3\spliter\videos\2904\2905slom_broke"
    # Skip already-processed files
    _done = {"725_01_M_20251217010000.h265", "737_01_M_20251217130000.h265"}
    os.makedirs(output_dir, exist_ok=True)

    config["output_folder"] = output_dir

    # Collect only valid video files (skip tiny/broken files < 1 MB)
    target_files = []
    for fname in sorted(os.listdir(input_dir)):
        if not fname.lower().endswith((".h265", ".hevc", ".mp4", ".mkv", ".avi")):
            continue
        if fname in _done:
            print(f"[SKIP] Already done: {fname}")
            continue
        fpath = os.path.join(input_dir, fname)
        size = os.path.getsize(fpath)
        if size < 1024 * 1024:
            print(f"[SKIP] Too small ({size} bytes): {fname}")
            continue
        print(f"[OK] {fname}  ({size/1024/1024:.1f} MB)")
        target_files.append(fpath)

    if not target_files:
        print("No valid video files found.")
        sys.exit(1)

    # Use a dummy empty scan folder, pass files via extra_video_files
    dummy_scan = os.path.join(input_dir, "_empty_scan_")
    os.makedirs(dummy_scan, exist_ok=True)
    config["input_folder"] = dummy_scan
    config["extra_video_files"] = target_files

    run_pipeline(config)

    print("\n=== DONE ===")
    print(f"Output: {output_dir}")
    for root, dirs, files in os.walk(output_dir):
        for fname in sorted(files):
            if fname.endswith(".jpg"):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, output_dir)
                print(f"  {rel}  ({os.path.getsize(fpath):,} bytes)")
