import os
import subprocess
import json
import hashlib


def _to_ffmpeg_path(path, ffmpeg_path):
    """Convert /mnt/d/... WSL paths to D:\\... for Windows ffmpeg.exe."""
    if ffmpeg_path.endswith(".exe") and path.startswith("/mnt/"):
        parts = path.split("/", 3)  # ['', 'mnt', 'd', 'rest']
        if len(parts) >= 3:
            drive = parts[2].upper()
            rest = parts[3] if len(parts) > 3 else ""
            return f"{drive}:\\" + rest.replace("/", "\\")
    return path


def ffprobe_info(path):
    """
    Возвращает словарь с width, height, fps.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-of", "json",
            path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        info = json.loads(result.stdout)

        stream = info["streams"][0]
        w = int(stream.get("width", 0))
        h = int(stream.get("height", 0))

        fr = stream.get("r_frame_rate", "0/1")
        num, den = fr.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 25.0

        return {"width": w, "height": h, "fps": fps}
    except Exception:
        return {"width": 0, "height": 0, "fps": 25.0}


def file_hash(path, block_size=65536):
    """
    Хэш файла для кэша конвертации.
    """
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def convert_h265_to_video(input_path, ffmpeg_path="ffmpeg", cache_dir="cache_h265"):
    """
    Идеальная конвертация .h265/.hevc:
    - кэш по хэшу файла
    - авто width/height/fps
    - сначала попытка MKV без перекодирования
    - если не вышло — MP4 с перекодированием
    - возвращает путь к готовому видео или None
    """
    os.makedirs(cache_dir, exist_ok=True)

    # 1) кэш по хэшу
    h = file_hash(input_path)
    cache_json = os.path.join(cache_dir, f"{h}.json")

    if os.path.exists(cache_json):
        try:
            with open(cache_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
            out_path = meta.get("output_path")
            if out_path and os.path.exists(out_path):
                print(f"[H265] Использую кэш конвертации: {out_path}")
                return out_path
        except Exception:
            pass

    info = ffprobe_info(input_path)
    width = info["width"] or None
    height = info["height"] or None
    fps = info["fps"] or 25.0

    folder = os.path.dirname(input_path)
    base = os.path.splitext(os.path.basename(input_path))[0]

    mkv_path = os.path.join(folder, base + "_fixed.mkv")
    mp4_path = os.path.join(folder, base + "_fixed.mp4")

    print("\n=== H265 -> видео ===")
    print(f"Исходный файл: {input_path}")
    print(f"Определено: {width}x{height}, fps={fps:.3f}")

    # 2) попытка собрать MKV без перекодирования
    print("[H265] Пробую упаковать в MKV (без перекодирования)...")

    ff_input = _to_ffmpeg_path(input_path, ffmpeg_path)
    ff_mkv = _to_ffmpeg_path(mkv_path, ffmpeg_path)
    ff_mp4 = _to_ffmpeg_path(mp4_path, ffmpeg_path)

    cmd_mkv = [
        ffmpeg_path,
        "-fflags", "+genpts",
        "-r", f"{fps}",
        "-i", ff_input,
        "-c", "copy",
        ff_mkv,
        "-y"
    ]

    try:
        subprocess.run(cmd_mkv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if os.path.exists(mkv_path) and os.path.getsize(mkv_path) > 0:
            print("[H265] MKV успешно создан.")
            out_path = mkv_path
        else:
            print("[H265] MKV не удалось создать, пробую MP4...")
            out_path = None
    except Exception as e:
        print(f"[H265] Ошибка MKV: {e}")
        out_path = None

    # 3) если MKV не получилось — перекодирование в MP4
    if out_path is None:
        print("[H265] Перекодирование в MP4 (libx265)...")

        cmd_mp4 = [
            ffmpeg_path,
            "-v", "error",
            "-f", "hevc",
            "-r", f"{fps}"
        ]

        if width and height:
            cmd_mp4 += ["-s", f"{width}x{height}"]

        cmd_mp4 += [
            "-i", ff_input,
            "-c:v", "libx265",
            "-preset", "medium",
            "-crf", "18",
            ff_mp4,
            "-y"
        ]

        try:
            subprocess.run(cmd_mp4, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 0:
                print("[H265] MP4 успешно создан.")
                out_path = mp4_path
            else:
                print("[H265] MP4 не удалось создать.")
                out_path = None
        except Exception as e:
            print(f"[H265] Ошибка MP4: {e}")
            out_path = None

    if out_path is None:
        print("[H265] Файл невозможно восстановить — поток повреждён.")
        return None

    # 4) сохраняем кэш
    meta = {
        "input": os.path.abspath(input_path),
        "output_path": os.path.abspath(out_path),
        "width": width,
        "height": height,
        "fps": fps
    }
    try:
        with open(cache_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return out_path