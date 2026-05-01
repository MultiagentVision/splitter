"""
Docker entrypoint: read INPUT_DIR / OUTPUT_DIR / FRAME_MODE from environment.
"""
import sys
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

sys.path.insert(0, os.path.dirname(__file__))

from config_utils import load_config
from pipeline import run_pipeline

config = load_config(os.path.join(os.path.dirname(__file__), "config.json"))

config["use_video_files"] = True
config["use_stream"] = False
config["gdrive_links"] = []
config["max_videos_per_run"] = 0
config["processes"] = int(os.environ.get("PROCESSES", "1"))
config["ffmpeg_path"] = "ffmpeg"
config["use_ffmpeg"] = False
config["use_seek"] = True

config["frame_mode"] = os.environ.get("FRAME_MODE", "rare")
config["quality_level"] = os.environ.get("QUALITY_LEVEL", "low")
config["frequent_interval_sec"] = int(os.environ.get("INTERVAL_SEC", "30"))

input_dir = os.environ.get("INPUT_DIR", "/data/input")
output_dir = os.environ.get("OUTPUT_DIR", "/data/output")
os.makedirs(output_dir, exist_ok=True)
config["output_folder"] = output_dir

print(f"[CONFIG] frame_mode={config['frame_mode']}  quality={config['quality_level']}")
print(f"[CONFIG] input_dir={input_dir}")
print(f"[CONFIG] output_dir={output_dir}")

target_files = []
for fname in sorted(os.listdir(input_dir)):
    ext = os.path.splitext(fname)[1].lower()
    if ext not in (".h265", ".hevc", ".mp4", ".mkv", ".avi"):
        continue
    fpath = os.path.join(input_dir, fname)
    size = os.path.getsize(fpath)
    if size < 1024 * 1024:
        print(f"[SKIP] Too small ({size} bytes): {fname}")
        continue
    print(f"[OK]   {fname}  ({size / 1024 / 1024:.1f} MB)")
    target_files.append(fpath)

if not target_files:
    print("No valid video files found in INPUT_DIR.")
    sys.exit(1)

dummy_scan = os.path.join(input_dir, "_empty_scan_")
os.makedirs(dummy_scan, exist_ok=True)
config["input_folder"] = dummy_scan
config["extra_video_files"] = target_files

run_pipeline(config)

print("\n=== DONE ===")
print(f"Output: {output_dir}")
count = 0
for root, dirs, files in os.walk(output_dir):
    for fn in sorted(files):
        if fn.endswith(".jpg"):
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, output_dir)
            print(f"  {rel}  ({os.path.getsize(fp) // 1024} KB)")
            count += 1
print(f"Total frames saved: {count}")
