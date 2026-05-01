"""
H.265 / HEVC → воспроизводимое видео.

Цепочка попыток (Вариант 4):
  1. ffprobe -f hevc  → метаданные (fps, разрешение) без конвертации
  2. MKV stream-copy с -f hevc → быстро, без потерь, правильный seeking
  3. MP4 re-encode libx264 (не libx265!) → fallback, быстрее + лучший seeking
  4. Все шаги с подробным logging (команда + stderr + размер результата)
"""
import hashlib
import json
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


def _to_ffmpeg_path(path, ffmpeg_path):
    """Convert /mnt/d/... WSL paths to D:\\... for Windows ffmpeg.exe."""
    if ffmpeg_path.endswith(".exe") and path.startswith("/mnt/"):
        parts = path.split("/", 3)
        if len(parts) >= 3:
            drive = parts[2].upper()
            rest = parts[3] if len(parts) > 3 else ""
            return f"{drive}:\\" + rest.replace("/", "\\")
    return path


def ffprobe_info(path: str, ffmpeg_path: str = "ffmpeg") -> dict:
    """
    Возвращает dict с width, height, fps, duration_sec, codec.
    Использует -f hevc как fallback для raw bitstream.
    """
    ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe") if "ffmpeg" in ffmpeg_path else "ffprobe"
    fp = _to_ffmpeg_path(path, ffprobe)

    def _run(extra_flags: list) -> dict | None:
        cmd = [
            ffprobe,
            "-v", "error",
            *extra_flags,
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name:format=duration",
            "-of", "json",
            fp,
        ]
        t0 = time.perf_counter()
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        elapsed = time.perf_counter() - t0
        logger.debug("ffprobe %s → exit=%d elapsed=%.1fs stderr=%s",
                     " ".join(extra_flags) or "(default)",
                     result.returncode, elapsed,
                     result.stderr.strip()[:300] or "(none)")
        if result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        if not streams:
            return None
        s = streams[0]
        w = int(s.get("width") or 0)
        h = int(s.get("height") or 0)
        fr = s.get("r_frame_rate", "25/1")
        try:
            num, den = fr.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 25.0
        except Exception:
            fps = 25.0
        duration = float(fmt.get("duration") or 0) or None
        codec = s.get("codec_name", "")
        return {"width": w, "height": h, "fps": fps, "duration_sec": duration, "codec": codec}

    # Попытка 1: автоопределение
    info = _run([])
    if info and info["width"] and info["height"]:
        logger.debug("ffprobe OK (auto): %dx%d fps=%.3f codec=%s dur=%s",
                     info["width"], info["height"], info["fps"],
                     info["codec"], info.get("duration_sec"))
        return info

    # Попытка 2: явный hevc формат (для raw bitstream)
    if path.lower().endswith((".h265", ".hevc")):
        info2 = _run(["-f", "hevc"])
        if info2:
            logger.debug("ffprobe OK (-f hevc): %dx%d fps=%.3f codec=%s dur=%s",
                         info2["width"], info2["height"], info2["fps"],
                         info2["codec"], info2.get("duration_sec"))
            return info2

    logger.warning("ffprobe: не удалось определить параметры для %s, fallback defaults", path)
    return {"width": 0, "height": 0, "fps": 25.0, "duration_sec": None, "codec": "hevc"}


def file_hash(path: str, block_size: int = 65536) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def _run_ffmpeg(cmd: list, label: str) -> tuple[bool, str]:
    """Запускает ffmpeg, возвращает (success, stderr_excerpt)."""
    logger.debug("[%s] команда: %s", label, " ".join(str(c) for c in cmd))
    t0 = time.perf_counter()
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        logger.error("[%s] timeout 3600s!", label)
        return False, "timeout"
    except Exception as e:
        logger.error("[%s] ошибка запуска: %s", label, e)
        return False, str(e)
    elapsed = time.perf_counter() - t0
    stderr_short = result.stderr.strip()[-600:] if result.stderr else "(none)"
    logger.debug("[%s] exit=%d elapsed=%.1fs stderr_tail: %s", label, result.returncode, elapsed, stderr_short)
    if result.returncode != 0:
        logger.warning("[%s] ffmpeg вернул ненулевой код %d. stderr_tail: %s",
                       label, result.returncode, stderr_short)
    return result.returncode == 0, stderr_short


def _verify_output(path: str, label: str) -> bool:
    """Проверяет существование файла и его размер > 0."""
    if not os.path.exists(path):
        logger.warning("[%s] выходной файл не создан: %s", label, path)
        return False
    size = os.path.getsize(path)
    if size == 0:
        logger.warning("[%s] выходной файл пустой: %s", label, path)
        return False
    logger.info("[%s] выходной файл: %s (%.1f МБ)", label, path, size / 1024 / 1024)
    return True


def convert_h265_to_video(input_path: str, ffmpeg_path: str = "ffmpeg", cache_dir: str = "cache_h265") -> str | None:
    """
    Конвертирует raw H.265/HEVC в видеофайл пригодный для seeking.

    Цепочка (Вариант 4):
      1. Кэш по хэшу файла
      2. MKV stream-copy с -f hevc (быстро, без потерь)
      3. MP4 re-encode libx264 (fallback)
    Возвращает путь к готовому файлу или None.
    """
    os.makedirs(cache_dir, exist_ok=True)
    logger.info("=== H265 конвертация: %s ===", input_path)

    # 1) Кэш
    try:
        h = file_hash(input_path)
    except Exception as e:
        logger.warning("Хэш файла не удался: %s", e)
        h = None

    if h:
        cache_json = os.path.join(cache_dir, f"{h}.json")
        if os.path.exists(cache_json):
            try:
                with open(cache_json, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                out_path = meta.get("output_path")
                if out_path and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    logger.info("Кэш найден: %s (%.1f МБ)", out_path, os.path.getsize(out_path) / 1024 / 1024)
                    return out_path
                else:
                    logger.warning("Кэш устарел (файл не найден или пуст): %s", out_path)
            except Exception as e:
                logger.warning("Ошибка чтения кэша: %s", e)
    else:
        cache_json = None

    # 2) ffprobe для параметров
    info = ffprobe_info(input_path, ffmpeg_path)
    width = info["width"] or None
    height = info["height"] or None
    fps = info["fps"] or 25.0

    logger.info("Параметры входа: %dx%d fps=%.3f codec=%s dur=%s",
                width or 0, height or 0, fps, info.get("codec"), info.get("duration_sec"))

    folder = os.path.dirname(input_path)
    base = os.path.splitext(os.path.basename(input_path))[0]
    ff_input = _to_ffmpeg_path(input_path, ffmpeg_path)
    mkv_path = os.path.join(folder, base + "_fixed.mkv")
    mp4_path = os.path.join(folder, base + "_fixed.mp4")
    ff_mkv = _to_ffmpeg_path(mkv_path, ffmpeg_path)
    ff_mp4 = _to_ffmpeg_path(mp4_path, ffmpeg_path)

    out_path = None

    # 3) Попытка MKV stream-copy с -f hevc
    logger.info("[MKV] Попытка stream-copy без перекодирования (-f hevc)...")
    cmd_mkv = [
        ffmpeg_path,
        "-f", "hevc",
        "-r", str(fps),
        "-i", ff_input,
        "-c", "copy",
        "-y", ff_mkv,
    ]
    ok_mkv, _ = _run_ffmpeg(cmd_mkv, "MKV")
    if ok_mkv and _verify_output(mkv_path, "MKV"):
        logger.info("[MKV] Успешно создан: %s", mkv_path)
        out_path = mkv_path
    else:
        logger.warning("[MKV] Не удалось — переходим к MP4 re-encode (libx264)")

    # 4) Fallback: MP4 re-encode libx264 (не libx265 — быстрее и лучший seeking)
    if out_path is None:
        logger.info("[MP4/libx264] Начало перекодирования...")
        cmd_mp4 = [
            ffmpeg_path,
            "-f", "hevc",
            "-r", str(fps),
        ]
        if width and height:
            cmd_mp4 += ["-s", f"{width}x{height}"]
        cmd_mp4 += [
            "-i", ff_input,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-movflags", "+faststart",
            "-y", ff_mp4,
        ]
        ok_mp4, stderr = _run_ffmpeg(cmd_mp4, "MP4/libx264")
        if ok_mp4 and _verify_output(mp4_path, "MP4/libx264"):
            logger.info("[MP4/libx264] Успешно создан: %s", mp4_path)
            out_path = mp4_path
        else:
            logger.error("[MP4/libx264] Не удалось конвертировать. stderr: %s", stderr[-400:])

    if out_path is None:
        logger.error("Не удалось конвертировать %s — файл недоступен для обработки", input_path)
        return None

    # 5) Сохранить кэш
    if cache_json:
        meta = {
            "input": os.path.abspath(input_path),
            "output_path": os.path.abspath(out_path),
            "width": width,
            "height": height,
            "fps": fps,
        }
        try:
            with open(cache_json, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Не удалось сохранить кэш: %s", e)

    return out_path
