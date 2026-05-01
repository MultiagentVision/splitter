"""
Full pipeline test: convert all .h265 videos and extract 3 frames each.
Mirrors exactly what video_splitter_service.py should do.
"""
import subprocess, os, sys

sys.path.insert(0, r'D:\AiChess\spliter3\spliter')
from h265_converter import convert_h265_to_video

videos_dir = r'D:\AiChess\spliter3\spliter\videos'
out_root = r'D:\AiChess\spliter3\spliter\videos_out'
cache_dir = r'D:\AiChess\spliter3\spliter\cache_h265'

videos = [f for f in os.listdir(videos_dir) if f.endswith('.h265')]
print(f"Found {len(videos)} .h265 files\n")

for fname in sorted(videos):
    fpath = os.path.join(videos_dir, fname)
    fsize_mb = os.path.getsize(fpath) / 1024 / 1024
    print(f"{'='*60}")
    print(f"File: {fname} ({fsize_mb:.1f} MB)")

    # Step 1: Convert
    converted = convert_h265_to_video(fpath, ffmpeg_path='ffmpeg', cache_dir=cache_dir)
    if not converted:
        print("  CONVERT FAILED")
        continue

    # Step 2: Get duration
    dp = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=noprint_wrappers=1:nokey=1', converted], capture_output=True, text=True)
    try:
        dur = float(dp.stdout.strip())
    except:
        print(f"  DURATION FAILED: {dp.stdout!r}")
        continue
    print(f"  Duration: {dur:.1f}s ({dur/3600:.2f}h)")

    # Step 3: Extract 3 frames (start / mid / end)
    stem = os.path.splitext(fname)[0]
    frame_dir = os.path.join(out_root, stem, 'jpeg')
    os.makedirs(frame_dir, exist_ok=True)

    slots = [
        ('start', 0.0),
        ('mid',   dur * 0.5),
        ('end',   max(dur - 1.0, 0.0)),
    ]
    all_ok = True
    for label, t in slots:
        out_jpg = os.path.join(frame_dir, f'frame_{label}.jpg')
        r = subprocess.run(['ffmpeg','-y','-ss',f'{t:.3f}','-i',converted,
            '-vframes','1','-q:v','2',out_jpg], capture_output=True)
        fsize = os.path.getsize(out_jpg) if os.path.exists(out_jpg) else 0
        status = "OK" if fsize > 10000 else "SMALL/EMPTY"
        if status != "OK":
            all_ok = False
        print(f"  Frame {label} @ {t:.0f}s: {fsize//1024}KB  [{status}]  exit={r.returncode}")
        if r.returncode != 0 and r.stderr:
            print(f"    stderr: {r.stderr.decode(errors='replace')[:150]}")

    if all_ok:
        print(f"  >>> RESULT: 3 GOOD FRAMES <<<")
    else:
        print(f"  >>> RESULT: SOME FRAMES FAILED <<<")
    print()

print("Done.")
