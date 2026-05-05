"""
MP4/libx264 conversion test.
Converts H.265 files from 01052026 using strategy="libx264" (primary),
outputs frames to 05052026_МП4_проба.

Measures conversion time per file and reports result quality.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(__file__))

from config_utils import load_config
from pipeline import extract_frames_for_video
from h265_converter import convert_h265_to_video

LOG_FILE = os.path.join(os.path.dirname(__file__), "mp4_test_log2.txt")

handlers = [
    logging.StreamHandler(sys.stdout),
    logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=handlers,
)
logger = logging.getLogger("run_mp4_test")

# Файлы для теста — берём 3 из уже скачанных
TEST_FILES = [
    r"D:\AiChess\spliter3\spliter\videos\01052026\994_01_M_20251221200000.h265",
    r"D:\AiChess\spliter3\spliter\videos\01052026\Copy of 767_06_R_20251214150000.h265",
    r"D:\AiChess\spliter3\spliter\videos\01052026\Copy of 468_04_R_20251208190000.h265",
]

OUTPUT_DIR = r"D:\AiChess\spliter3\spliter\videos\05052026_МП4_проба"
CACHE_DIR  = r"D:\AiChess\spliter3\spliter\videos\05052026_МП4_проба\cache_h265"


if __name__ == "__main__":
    config = load_config(os.path.join(os.path.dirname(__file__), "config.json"))
    config["use_video_files"] = True
    config["frame_mode"] = "rare"
    config["quality_level"] = "low"
    config["output_folder"] = OUTPUT_DIR

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    total_start = time.time()
    results = []

    for fpath in TEST_FILES:
        if not os.path.isfile(fpath):
            logger.warning("[SKIP] File not found: %s", fpath)
            continue

        fname = os.path.basename(fpath)
        size_mb = os.path.getsize(fpath) / 1024 / 1024
        logger.info("")
        logger.info("=" * 60)
        logger.info("=== Processing: %s (%.1f MB) ===", fname, size_mb)
        logger.info("=" * 60)

        # Конвертация с strategy=libx264 (PRIMARY MP4/libx264, FALLBACK MKV)
        conv_start = time.time()
        converted = convert_h265_to_video(
            fpath,
            ffmpeg_path=config.get("ffmpeg_path", "ffmpeg"),
            cache_dir=CACHE_DIR,
            strategy="libx264",
        )
        conv_elapsed = time.time() - conv_start

        if converted:
            conv_mb = os.path.getsize(converted) / 1024 / 1024
            logger.info("[CONVERT] OK: %s (%.1f MB) за %.1f сек", converted, conv_mb, conv_elapsed)
            process_path = converted
        else:
            logger.warning("[CONVERT] FAILED (%.1f сек) — пробуем оригинал", conv_elapsed)
            process_path = fpath

        # Извлечение кадров
        frame_start = time.time()
        config_run = {**config, "output_folder": OUTPUT_DIR}
        extract_frames_for_video((process_path, config_run))
        frame_elapsed = time.time() - frame_start

        results.append({
            "file": fname,
            "size_mb": size_mb,
            "conv_sec": conv_elapsed,
            "frame_sec": frame_elapsed,
            "converted_ok": converted is not None,
        })
        logger.info("[TIMING] %s — конв: %.1f сек, кадры: %.1f сек", fname, conv_elapsed, frame_elapsed)

    total_elapsed = time.time() - total_start

    # Итоговый отчёт
    logger.info("")
    logger.info("=" * 60)
    logger.info("=== ИТОГОВЫЙ ОТЧЁТ ===")
    logger.info("=" * 60)
    for r in results:
        status = "OK" if r["converted_ok"] else "FALLBACK"
        logger.info(
            "  [%s] %s (%.1f MB) — конверт: %.1f с, кадры: %.1f с",
            status, r["file"], r["size_mb"], r["conv_sec"], r["frame_sec"],
        )

    logger.info("Всего: %.1f сек (%.1f мин)", total_elapsed, total_elapsed / 60)
    logger.info("Выходная папка: %s", OUTPUT_DIR)

    # Список сохранённых кадров
    logger.info("")
    logger.info("Сохранённые кадры:")
    frame_count = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in sorted(files):
            if f.endswith((".jpg", ".png")):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, OUTPUT_DIR)
                logger.info("  %s  (%d KB)", rel, os.path.getsize(full) // 1024)
                frame_count += 1
    logger.info("Итого кадров: %d", frame_count)
