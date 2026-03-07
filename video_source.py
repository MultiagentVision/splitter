import cv2
import subprocess
import numpy as np
import json
import os

from video_sources import get_video_fps_and_frame_count


def ffprobe_get_resolution(path):
    """
    Определяет разрешение видео через ffprobe.
    Работает с MP4/MKV/RTSP/HLS/raw HEVC.
    """
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
        return w, h
    except Exception:
        return 1920, 1080  # fallback


class VideoSource:
    def __init__(self, path, use_ffmpeg=False, ffmpeg_path="ffmpeg"):
        self.path = path
        self.use_ffmpeg = use_ffmpeg
        self.ffmpeg_path = ffmpeg_path

        self.last_frame = None

        # Определяем разрешение заранее
        self.width, self.height = ffprobe_get_resolution(path)

        if not self.use_ffmpeg:
            # Обычный OpenCV
            self.cap = cv2.VideoCapture(path)
            self.ffmpeg_process = None
            self._fps = 0.0
            self._total_frames = 0
        else:
            # ffmpeg → rawvideo → numpy; FPS и число кадров через ffprobe
            self.cap = None
            self._fps, self._total_frames = get_video_fps_and_frame_count(path)
            self.ffmpeg_process = self._start_ffmpeg_stream(path)

    def _start_ffmpeg_stream(self, url):
        """
        Запускает ffmpeg, который отдаёт кадры в формате rawvideo (BGR24).
        """
        cmd = [
            self.ffmpeg_path,
            "-i", url,
            "-loglevel", "quiet",
            "-an",
            "-f", "image2pipe",
            "-pix_fmt", "bgr24",
            "-vcodec", "rawvideo",
            "-"
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**8)

    def read(self):
        """
        Чтение кадра.
        Если ffmpeg — читаем width*height*3 байт.
        """
        if not self.use_ffmpeg:
            ret, frame = self.cap.read()
            if ret:
                self.last_frame = frame
            return ret, frame

        # Читаем ровно один кадр
        frame_size = self.width * self.height * 3
        raw = self.ffmpeg_process.stdout.read(frame_size)

        if not raw or len(raw) < frame_size:
            return False, None

        frame = np.frombuffer(raw, np.uint8)
        try:
            frame = frame.reshape((self.height, self.width, 3))
        except:
            return False, None

        self.last_frame = frame
        return True, frame

    def get_fps(self):
        if self.use_ffmpeg:
            return self._fps
        return self.cap.get(cv2.CAP_PROP_FPS)

    def get_total_frames(self):
        if self.use_ffmpeg:
            return self._total_frames
        return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def get_duration_sec(self):
        fps = self.get_fps()
        total = self.get_total_frames()
        if fps <= 0:
            return 0
        return total / fps

    def release(self):
        if not self.use_ffmpeg:
            if self.cap:
                self.cap.release()
        else:
            if self.ffmpeg_process:
                self.ffmpeg_process.kill() 