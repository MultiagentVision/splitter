import subprocess, os

h265 = r'D:\AiChess\spliter3\spliter\videos\15_9001022_01_M_20251223000000.h265'
out_dir = r'D:\AiChess\spliter3\spliter\videos_out\direct_h265'
os.makedirs(out_dir, exist_ok=True)

print("=== Approach 1: monorepo _remux_raw_hevc_to_mp4_copy: -f hevc -c copy -> mp4 ===")
mp4 = out_dir + '/remux_f_hevc.mp4'
r = subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error',
    '-f','hevc','-i',h265,'-c','copy',mp4], capture_output=True)
print(f'  exit={r.returncode}')
print(f'  stderr: {r.stderr.decode(errors="replace")[:300]}')
exists = os.path.exists(mp4)
size = os.path.getsize(mp4) if exists else 0
print(f'  file: exists={exists}, size={size} bytes')

print()
print("=== Approach 2: monorepo _remux_to_mkv: probesize+genpts (no -f hevc) ===")
mkv2 = out_dir + '/remux_probesize.mkv'
r2 = subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error',
    '-probesize','200M','-analyzeduration','200M',
    '-fflags','+genpts','-i',h265,'-c','copy',mkv2], capture_output=True)
print(f'  exit={r2.returncode}')
print(f'  stderr: {r2.stderr.decode(errors="replace")[:300]}')
exists2 = os.path.exists(mkv2)
size2 = os.path.getsize(mkv2) if exists2 else 0
print(f'  file: exists={exists2}, size={size2} bytes')

print()
print("=== Approach 3: NEW monorepo: -f hevc +genpts (our latest fix) ===")
mkv3 = out_dir + '/remux_f_hevc_genpts.mkv'
r3 = subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error',
    '-fflags','+genpts','-f','hevc','-i',h265,'-c','copy',mkv3], capture_output=True)
print(f'  exit={r3.returncode}')
print(f'  stderr: {r3.stderr.decode(errors="replace")[:300]}')
exists3 = os.path.exists(mkv3)
size3 = os.path.getsize(mkv3) if exists3 else 0
print(f'  file: exists={exists3}, size={size3} bytes')

print()
print("=== Approach 4: LOCAL (works): -fflags +genpts -r 20 -i h265 -c copy mkv (no check=True) ===")
mkv4 = out_dir + '/remux_local_style.mkv'
r4 = subprocess.run(['ffmpeg','-fflags','+genpts','-r','20','-i',h265,'-c','copy',mkv4,'-y'],
    capture_output=True)
print(f'  exit={r4.returncode}')
print(f'  stderr: {r4.stderr.decode(errors="replace")[:300]}')
exists4 = os.path.exists(mkv4)
size4 = os.path.getsize(mkv4) if exists4 else 0
print(f'  file: exists={exists4}, size={size4} bytes')

# Now test frame extraction from each successful result
print()
print("=== Frame extraction test from each approach ===")
for label, path in [("mp4_f_hevc", mp4), ("mkv_probesize", mkv2), ("mkv_f_hevc_genpts", mkv3), ("mkv_local", mkv4)]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print(f'  {label}: SKIPPED (file missing or empty)')
        continue
    # Get duration
    dp = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=noprint_wrappers=1:nokey=1',path], capture_output=True, text=True)
    try:
        dur = float(dp.stdout.strip())
    except:
        dur = 0
    if dur <= 0:
        print(f'  {label}: duration=0, SKIP')
        continue
    # Extract middle frame
    mid = out_dir + f'/frame_mid_{label}.jpg'
    er = subprocess.run(['ffmpeg','-y','-ss',f'{dur*0.5:.3f}','-i',path,
        '-vframes','1','-q:v','2',mid], capture_output=True)
    fsize = os.path.getsize(mid) if os.path.exists(mid) else 0
    print(f'  {label}: dur={dur:.0f}s, frame_size={fsize/1024:.0f}KB, exit={er.returncode}')
