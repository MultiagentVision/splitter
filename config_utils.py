import json
import os
import re
from typing import Any, Dict


def load_config(path: str = "config.json") -> Dict[str, Any]:
    """
    Загрузка конфигурации из JSON-файла.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_video_name(path: str) -> str:
    """
    Генерация безопасного имени для папки/файла по пути или URL.
    Для YouTube вытаскивает id ролика, для остальных путей чистит имя файла.
    """
    if "youtube.com" in path or "youtu.be" in path:
        m = re.search(r"v=([A-Za-z0-9_-]{6,})", path)
        if m:
            return m.group(1)

        m = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", path)
        if m:
            return m.group(1)

        return "youtube_video"

    name = os.path.basename(path)
    name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    return name[:50]

