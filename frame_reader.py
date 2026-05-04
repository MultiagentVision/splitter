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


def get_frame_ffmpeg(
    video_path: str,
    frame_idx: int,
    fps: float,
    ffmpeg_path: str = "ffmpeg",
) -> tuple[bool, "np.ndarray | None"]:
    """
    Извлекает один кадр через ffmpeg (без OpenCV).
    Для raw .h265/.hevc добавляет -f hevc перед -i.
    """
    width, height = ffprobe_get_resolution(video_path, ffmpeg_path)
    frame_size = width * height * 3
    timestamp = frame_idx / fps if fps > 0 else 0.0

    extra_input_flags: list = []
    if _is_raw_hevc(video_path):
        extra_input_flags = ["-f", "hevc"]

    cmd = [
        ffmpeg_path,
        "-ss", f"{timestamp:.3f}",
        *extra_input_flags,
        "-i", video_path,
        "-vframes", "1",
        "-f", "image2pipe",
        "-pix_fmt", "bgr24",
        "-vcodec", "rawvideo",
        "-loglevel", "error",
        "-",
    ]

    logger.debug(
        "get_frame_ffmpeg: idx=%d t=%.3fs res=%dx%d cmd: %s",
        frame_idx, timestamp, width, height, " ".join(str(c) for c in cmd),
    )

    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr_msg = (e.stderr or b"").decode(errors="replace")[-300:]
        logger.warning(
            "get_frame_ffmpeg: ffmpeg error idx=%d t=%.3fs stderr: %s",
            frame_idx, timestamp, stderr_msg,
        )
        return False, None
    except Exception as e:
        logger.warning("get_frame_ffmpeg: exception idx=%d: %s", frame_idx, e)
        return False, None

    got = len(raw)
    logger.debug("get_frame_ffmpeg: idx=%d получено байт=%d ожидалось=%d", frame_idx, got, frame_size)

    if not raw or got < frame_size:
        logger.warning(
            "get_frame_ffmpeg: недостаточно данных idx=%d t=%.3fs got=%d expected=%d",
            frame_idx, timestamp, got, frame_size,
        )
        return False, None

    try:
        frame = np.frombuffer(raw[:frame_size], np.uint8).reshape((height, width, 3))
    except Exception as e:
        logger.warning(
            "get_frame_ffmpeg: reshape error idx=%d raw=%d expected=%dx%dx3=%d: %s",
            frame_idx, got, height, width, frame_size, e,
        )
        return False, None

    b_mean = float(np.mean(frame[:, :, 0]))
    g_mean = float(np.mean(frame[:, :, 1]))
    r_mean = float(np.mean(frame[:, :, 2]))
    logger.debug(
        "get_frame_ffmpeg: idx=%d OK shape=%dx%d B=%.1f G=%.1f R=%.1f",
        frame_idx, width, height, b_mean, g_mean, r_mean,
    )
    return True, frame


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
