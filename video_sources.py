import json
import os
import subprocess
from typing import Optional, List, Union, Tuple

import cv2
from yt_dlp import YoutubeDL
import gdown


def detect_url_type(url: str) -> str:
    """
    Определение типа URL:
    - gdrive: ссылки Google Drive
    - youtube: YouTube
    - rtsp / hls / file_url / http / unknown
    """
    url_low = url.lower()

    if "drive.google.com" in url_low:
        return "gdrive"

    if url_low.startswith("rtsp://"):
        return "rtsp"

    if url_low.endswith(".m3u8"):
        return "hls"

    if url_low.endswith((".mp4", ".mov", ".avi", ".mkv", ".h265", ".hevc")):
        return "file_url"

    if "youtube.com" in url_low or "youtu.be" in url_low:
        return "youtube"

    if url_low.startswith("http://") or url_low.startswith("https://"):
        return "http"

    return "unknown"


def get_youtube_stream_url(youtube_url: str) -> str:
    """
    Получение прямого потока для YouTube через yt_dlp.
    """
    ydl_opts = {
        "quiet": True,
        "format": "best[ext=mp4]/best",
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return info["url"]


def check_stream_available(source, retries: int = 5) -> bool:
    """
    Простая проверка доступности потока через OpenCV.
    """
    import time

    print(f"Проверка источника: {source}")

    for i in range(retries):
        cap = cv2.VideoCapture(source)
        ok, _ = cap.read()
        cap.release()

        if ok:
            print("Источник доступен.")
            return True

        print(f"Попытка {i + 1}/{retries} неудачна, повтор...")
        time.sleep(1)

    print("Источник недоступен.")
    return False


def get_video_codec(path: str) -> Optional[str]:
    """
    Определение видеокодека файла через ffprobe.
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=nw=1:nk=1",
            path,
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        codec = result.stdout.strip()
        return codec if codec else None
    except Exception:
        return None


def get_video_fps_and_frame_count(path: str) -> Tuple[float, int]:
    """
    Возвращает (fps, total_frames) через ffprobe.
    Сначала пробует format=duration + stream=r_frame_rate (быстро).
    Если duration отсутствует или 0 — fallback на -count_frames (точнее, но декодирует поток).
    При ошибке возвращает (0, 0).
    """
    try:
        # Быстрый способ: duration контейнера + r_frame_rate
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration:stream=r_frame_rate",
            "-of", "json",
            path,
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
        )
        if result.returncode != 0:
            return (0, 0)

        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        fmt = data.get("format") or {}
        duration = float(fmt.get("duration") or 0)

        fps = 0.0
        if streams:
            fr = streams[0].get("r_frame_rate", "0/1")
            if "/" in fr:
                num, den = fr.split("/", 1)
                fps = float(num) / float(den) if float(den) != 0 else 0.0
            else:
                fps = float(fr) if fr else 0.0

        if duration > 0 and fps > 0:
            total_frames = int(round(duration * fps))
            return (fps, total_frames)

        # Fallback: -count_frames (точный подсчёт, но декодирует)
        cmd2 = [
            "ffprobe",
            "-v", "error",
            "-count_frames",
            "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames,r_frame_rate",
            "-of", "json",
            path,
        ]
        result2 = subprocess.run(
            cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600
        )
        if result2.returncode != 0:
            return (fps if fps else 0, 0)

        data2 = json.loads(result2.stdout)
        streams2 = data2.get("streams") or []
        if not streams2:
            return (fps if fps else 0, 0)

        s = streams2[0]
        nb = int(s.get("nb_read_frames") or 0)
        fr2 = s.get("r_frame_rate", "0/1")
        if "/" in fr2:
            num, den = fr2.split("/", 1)
            fps2 = float(num) / float(den) if float(den) != 0 else fps
        else:
            fps2 = float(fr2) if fr2 else fps
        return (fps2, nb)
    except Exception:
        return (0, 0)


def download_gdrive_video(url: str, download_dir: str = "videos") -> List[str]:
    """
    Загрузка одного ресурса Google Drive.

    Поддерживаются:
    - ссылки на файл (file/d/ID или ?id=ID);
    - ссылки на папку (drive.google.com/drive/folders/...).

    Возвращает список путей к загруженным файлам.
    """
    os.makedirs(download_dir, exist_ok=True)

    try:
        if "/folders/" in url:
            # Скачиваем все файлы из папки
            print(f"[GDrive] Скачиваю папку: {url}")
            paths = gdown.download_folder(url, output=download_dir, quiet=False, use_cookies=False)
            # download_folder возвращает список путей или None
            if not paths:
                raise RuntimeError("gdown.download_folder вернул пустой результат")
            # Нормализуем к списку строк
            if isinstance(paths, str):
                paths = [paths]
            return [os.path.abspath(p) for p in paths]
        else:
            # Скачиваем один файл
            print(f"[GDrive] Скачиваю файл: {url}")
            local_path = gdown.download(url, output=download_dir, quiet=False)
            if not local_path:
                raise RuntimeError("Не удалось скачать файл с Google Drive")
            return [os.path.abspath(local_path)]
    except Exception as e:
        print(f"[GDrive] Ошибка скачивания {url}: {e}")
        return []


def download_gdrive_videos(urls: List[str], download_dir: str = "videos") -> List[str]:
    """
    Скачивает несколько ссылок Google Drive (файлы и/или папки), возвращает список локальных путей.
    """
    local_paths: List[str] = []
    for u in urls:
        paths = download_gdrive_video(u, download_dir=download_dir)
        local_paths.extend(paths)
    return local_paths

