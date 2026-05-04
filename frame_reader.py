"""
Извлечение кадров из видеофайлов.

get_frame_ffmpeg: поддерживает raw .h265/.hevc через -f hevc флаг.
Все шаги логируются (команда, размер данных, статистика кадра).
"""
import logging
import subprocess

import cv2
import json
import numpy as np

logger = logging.getLogger(__name__)

# Кэш для resolution, чтобы не вызывать ffprobe каждый раз
_resolution_cache: dict = {}


def _is_raw_hevc(path: str) -> bool:
    return path.lower().endswith((".h265", ".hevc"))


def ffprobe_get_resolution(path: str, ffmpeg_path: str = "ffmpeg") -> tuple[int, int]:
    """
    Определяет разрешение видео через ffprobe.
    Для raw .h265/.hevc использует -f hevc как fallback.
    Кэширует результат.
    """
    if path in _resolution_cache:
        logger.debug("ffprobe_get_resolution: кэш для %s → %s", path, _resolution_cache[path])
        return _resolution_cache[path]

    import os as _os
    _ffmpeg_dir = _os.path.dirname(ffmpeg_path)
    _ffmpeg_base = _os.path.basename(ffmpeg_path)
    ffprobe = _os.path.join(_ffmpeg_dir, _ffmpeg_base.replace("ffmpeg", "ffprobe")) if "ffmpeg" in _ffmpeg_base else "ffprobe"

    def _try(extra_flags: list) -> tuple[int, int] | None:
        cmd = [
            ffprobe,
            "-v", "error",
            *extra_flags,
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            path,
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            if result.returncode != 0:
                logger.debug("ffprobe_get_resolution %s exit=%d stderr=%s",
                             extra_flags, result.returncode, result.stderr.strip()[:200])
                return None
            info = json.loads(result.stdout)
            s = info["streams"][0]
            w, h = int(s.get("width") or 0), int(s.get("height") or 0)
            if w > 0 and h > 0:
                return w, h
        except Exception as e:
            logger.debug("ffprobe_get_resolution exception %s: %s", extra_flags, e)
        return None

    wh = _try([])
    if wh is None and _is_raw_hevc(path):
        logger.debug("ffprobe_get_resolution: retry с -f hevc для %s", path)
        wh = _try(["-f", "hevc"])

    if wh is None:
        logger.warning("ffprobe_get_resolution: не определено для %s, fallback 1920x1080", path)
        wh = (1920, 1080)

    logger.debug("ffprobe_get_resolution: %s → %dx%d", path, wh[0], wh[1])
    _resolution_cache[path] = wh
    return wh


def _build_seek_cmd(
    ffmpeg_path: str,
    video_path: str,
    timestamp: float,
    extra_input_flags: list,
    slow_seek: bool = False,
    pre_seek_s: float = 60.0,
) -> list:
    """
    Строит ffmpeg команду для извлечения одного кадра.

    slow_seek=False: fast seek — ss перед -i (быстро, но может попасть на битый IDR).
    slow_seek=True:  двухшаговый seek:
      1. fast pre-seek к (timestamp - pre_seek_s) — прыгаем к чистому IDR ~60с назад
      2. slow fine-seek на pre_seek_s вперёд — декодируем последовательно,
         P/B-кадры получают правильный reference от чистого IDR.
    """
    base_flags = ["-fflags", "+discardcorrupt", "-err_detect", "ignore_err"]
    output_flags = [
        "-vframes", "1",
        "-f", "image2pipe",
        "-pix_fmt", "bgr24",
        "-vcodec", "rawvideo",
        "-loglevel", "error",
        "-",
    ]
    if slow_seek:
        pre_ts = max(0.0, timestamp - pre_seek_s)
        fine_s = timestamp - pre_ts
        return [
            ffmpeg_path,
            *base_flags,
            "-ss", f"{pre_ts:.3f}",
            *extra_input_flags,
            "-i", video_path,
            "-ss", f"{fine_s:.3f}",
            *output_flags,
        ]
    return [
        ffmpeg_path,
        *base_flags,
        "-ss", f"{timestamp:.3f}",
        *extra_input_flags,
        "-i", video_path,
        *output_flags,
    ]


def _run_frame_cmd(
    cmd: list,
    frame_idx: int,
    timestamp: float,
    frame_size: int,
    width: int,
    height: int,
    label: str = "",
) -> tuple[bool, "np.ndarray | None"]:
    """Выполняет ffmpeg, проверяет размер и отклоняет blank (std < 25) кадры."""
    logger.debug("get_frame_ffmpeg [%s] idx=%d t=%.3fs cmd: %s",
                 label, frame_idx, timestamp, " ".join(str(c) for c in cmd))
    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr_msg = (e.stderr or b"").decode(errors="replace")[-300:]
        logger.warning("get_frame_ffmpeg [%s] ffmpeg error idx=%d t=%.3fs: %s",
                       label, frame_idx, timestamp, stderr_msg)
        return False, None
    except Exception as e:
        logger.warning("get_frame_ffmpeg [%s] exception idx=%d: %s", label, frame_idx, e)
        return False, None

    got = len(raw)
    if not raw or got < frame_size:
        logger.warning("get_frame_ffmpeg [%s] мало данных idx=%d t=%.3fs got=%d expected=%d",
                       label, frame_idx, timestamp, got, frame_size)
        return False, None

    try:
        frame = np.frombuffer(raw[:frame_size], np.uint8).reshape((height, width, 3))
    except Exception as e:
        logger.warning("get_frame_ffmpeg [%s] reshape error idx=%d: %s", label, frame_idx, e)
        return False, None

    b_mean = float(np.mean(frame[:, :, 0]))
    g_mean = float(np.mean(frame[:, :, 1]))
    r_mean = float(np.mean(frame[:, :, 2]))
    std_val = float(np.std(frame))

    # Отклонить blank: низкая дисперсия = серый/зелёный/чёрный равномерный цвет.
    # Шахматная доска: std >> 50; артефакт libhevc (серые CTU) — std < 15-25.
    if std_val < 25.0:
        logger.warning("get_frame_ffmpeg [%s] BLANK idx=%d t=%.3fs std=%.1f B=%.1f G=%.1f R=%.1f",
                       label, frame_idx, timestamp, std_val, b_mean, g_mean, r_mean)
        return False, None

    logger.debug("get_frame_ffmpeg [%s] OK idx=%d t=%.3fs std=%.1f B=%.1f G=%.1f R=%.1f",
                 label, frame_idx, timestamp, std_val, b_mean, g_mean, r_mean)
    return True, frame


def get_frame_ffmpeg(
    video_path: str,
    frame_idx: int,
    fps: float,
    ffmpeg_path: str = "ffmpeg",
) -> tuple[bool, "np.ndarray | None"]:
    """
    Извлекает один кадр через ffmpeg. 3-уровневый retry для HEVC без GPU:

    Tier 1 — Fast seek (ss before -i): быстро, попадает на ближайший IDR.
              Если IDR чистый — готово. Если corrupted CTU → blank → retry.

    Tier 2 — Slow seek 60s window (ss after -i): fast pre-seek к T-60s,
              затем последовательный decode 60s. P/B-кадры получают reference
              от чистого IDR из окна, а не от потенциально битого IDR у T.

    Tier 3 — Nearby timestamps ±5…±20s: сдвигаемся по времени пока не найдём
              IDR без corrupted CTU. Для шахматной статичной камеры кадры
              эквивалентны — нужен просто чистый IDR в ±20с окне.
    """
    width, height = ffprobe_get_resolution(video_path, ffmpeg_path)
    frame_size = width * height * 3
    timestamp = frame_idx / fps if fps > 0 else 0.0

    extra_input_flags: list = []
    if _is_raw_hevc(video_path):
        extra_input_flags = ["-f", "hevc"]

    # Tier 1: fast seek
    cmd = _build_seek_cmd(ffmpeg_path, video_path, timestamp, extra_input_flags, slow_seek=False)
    ok, frame = _run_frame_cmd(cmd, frame_idx, timestamp, frame_size, width, height, "fast")
    if ok:
        return True, frame

    # Tier 2: slow seek with 60s pre-seek window
    logger.info("get_frame_ffmpeg: fast blank → slow-seek(60s) idx=%d t=%.3fs", frame_idx, timestamp)
    cmd = _build_seek_cmd(ffmpeg_path, video_path, timestamp, extra_input_flags,
                          slow_seek=True, pre_seek_s=60.0)
    ok, frame = _run_frame_cmd(cmd, frame_idx, timestamp, frame_size, width, height, "slow-60s")
    if ok:
        return True, frame

    # Tier 3: nearby timestamps ±5, ±10, ±15, ±20s (с slow seek)
    for dt in [5, -5, 10, -10, 15, -15, 20, -20]:
        ts_alt = max(0.0, timestamp + dt)
        if abs(ts_alt - timestamp) < 1.0:
            continue
        logger.info("get_frame_ffmpeg: nearby dt=%+ds → ts=%.3fs idx=%d", dt, ts_alt, frame_idx)
        cmd = _build_seek_cmd(ffmpeg_path, video_path, ts_alt, extra_input_flags,
                              slow_seek=True, pre_seek_s=60.0)
        ok, frame = _run_frame_cmd(cmd, frame_idx, ts_alt, frame_size, width, height, f"nearby{dt:+d}s")
        if ok:
            logger.info("get_frame_ffmpeg: чистый кадр найден dt=%+ds (t=%.3f→%.3f) idx=%d",
                        dt, timestamp, ts_alt, frame_idx)
            return True, frame

    logger.warning("get_frame_ffmpeg: все %d попыток провалились idx=%d t=%.3fs",
                   1 + 1 + 8, frame_idx, timestamp)
    return False, None


def get_frame_seek(cap: "cv2.VideoCapture", frame_idx: int, pre_offset_frames: int = 3) -> tuple[bool, "np.ndarray | None"]:
    """
    SEEK через OpenCV.
    Перематывает немного ДО целевого кадра, затем читает до frame_idx.
    """
    try:
        effective_idx = max(0, frame_idx - pre_offset_frames)
        cap.set(cv2.CAP_PROP_POS_FRAMES, effective_idx)
        current_idx = effective_idx
        frame = None
        while current_idx <= frame_idx:
            ret, frame = cap.read()
            if not ret:
                logger.debug("get_frame_seek: EOF на idx=%d (target=%d)", current_idx, frame_idx)
                return False, None
            current_idx += 1
        return True, frame
    except Exception as e:
        logger.warning("get_frame_seek: exception idx=%d: %s", frame_idx, e)
        return False, None


def get_frame_sequential(
    cap: "cv2.VideoCapture",
    target_idx: int,
    current_idx: int,
    last_frame: "np.ndarray",
) -> tuple[bool, "np.ndarray | None"]:
    """Последовательное чтение кадров (для потоков)."""
    if target_idx == current_idx:
        return True, last_frame
    if target_idx < current_idx:
        return False, None
    while current_idx < target_idx:
        ret, frame = cap.read()
        if not ret:
            return False, None
        current_idx += 1
    return True, frame
