import logging
import os


def create_video_logger(video_name: str, base_dir: str) -> logging.Logger:
    """
    Создаёт отдельный логгер для конкретного видео,
    который пишет лог в файл <base_dir>/<video_name>.txt.
    """
    log_path = os.path.join(base_dir, f"{video_name}.txt")

    logger = logging.getLogger(video_name)
    logger.setLevel(logging.INFO)

    # очищаем старые хендлеры, чтобы не плодились дубликаты
    if logger.handlers:
        logger.handlers.clear()

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(formatter)

    logger.addHandler(fh)

    return logger

