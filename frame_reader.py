import subprocess
import numpy as np
import cv2
import json


# Кэш для resolution, чтобы не вызывать ffprobe каждый раз
_resolution_cache = {}


def ffprobe_get_resolution(path):
    """
    Определяет разрешение видео через ffprobe.
    Работает с MP4/MKV/RTSP/HLS/raw HEVC.
    Кэширует результат для ускорения.
    """
    if path in _resolution_cache:
        return _resolution_cache[path]

    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        info = json.loads(result.stdout)

        w = info["streams"][0]["width"]
        h = info["streams"][0]["height"]
        _resolution_cache[path] = (w, h)
        return w, h
    except Exception:
        result = (1920, 1080)  # fallback
        _resolution_cache[path] = result
        return result


# ---------------------------------------------------------
# 1) Точечное получение кадра через ffmpeg (без OpenCV)
# ---------------------------------------------------------
def get_frame_ffmpeg(video_path, frame_idx, fps, ffmpeg_path="ffmpeg"):
    """
    Получает кадр через ffmpeg, НЕ используя OpenCV.
    Гарантирует, что возвращаемый кадр соответствует запрошенному индексу.
    """

    width, height = ffprobe_get_resolution(video_path)
    frame_size = width * height * 3

    # Время точно для запрошенного кадра
    timestamp = frame_idx / fps

    cmd = [
        ffmpeg_path,
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-f", "image2pipe",
        "-pix_fmt", "bgr24",
        "-vcodec", "rawvideo",
        "-loglevel", "quiet",
        "-"
    ]

    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except Exception:
        return False, None

    if not raw or len(raw) < frame_size:
        return False, None

    frame = np.frombuffer(raw, np.uint8)
    try:
        frame = frame.reshape((height, width, 3))
    except Exception:
        return False, None

    return True, frame


# ---------------------------------------------------------
# 2) Получение кадра через SEEK OpenCV
# ---------------------------------------------------------
def get_frame_seek(cap, frame_idx, pre_offset_frames: int = 3):
    """
    SEEK через OpenCV.
    Перематывает немного ДО целевого кадра, но возвращает именно кадр
    с индексом frame_idx, чтобы не сдвигать соответствие индексов.
    """
    try:
        # Стартуем немного раньше, чтобы декодеру было проще,
        # но затем дочитываем до точного индекса.
        effective_idx = max(0, frame_idx - pre_offset_frames)
        cap.set(cv2.CAP_PROP_POS_FRAMES, effective_idx)

        current_idx = effective_idx
        frame = None

        while current_idx <= frame_idx:
            ret, frame = cap.read()
            if not ret:
                return False, None
            current_idx += 1

        return True, frame
    except Exception:
        return False, None


# ---------------------------------------------------------
# 3) Последовательное чтение (OpenCV)
# ---------------------------------------------------------
def get_frame_sequential(cap, target_idx, current_idx, last_frame):
    """
    Последовательное чтение кадров.
    """
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
