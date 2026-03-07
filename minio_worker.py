"""
Воркер MinIO: проверка новых файлов (polling), обработка по алгоритму spliter, выгрузка результатов в MinIO.

Использование:
  python minio_worker.py              # цикл опроса (интервал из config)
  python minio_worker.py --once       # один проход

Требуется в config.json секция "minio" и credentials (env или ~/.aws/credentials).
"""
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from config_utils import load_config, safe_video_name
from pipeline import extract_frames_for_video
from h265_converter import convert_h265_to_video
from upload_to_s3 import find_aws_credentials, find_working_endpoint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".h265", ".hevc")


def get_s3_client(config_minio: dict):
    """S3/MinIO клиент из конфига и credentials."""
    endpoint = (
        config_minio.get("endpoint_url")
        or os.getenv("S3_ENDPOINT_URL")
    )
    bucket = config_minio.get("bucket_name", "chess-ai")
    access_key, secret_key = find_aws_credentials()
    if not access_key or not secret_key:
        raise RuntimeError(
            "MinIO/S3 credentials не найдены. "
            "Задайте AWS_ACCESS_KEY_ID и AWS_SECRET_ACCESS_KEY или настройте ~/.aws/credentials"
        )
    if not endpoint:
        endpoint = find_working_endpoint(bucket, access_key, secret_key)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    ), endpoint, bucket


def list_video_keys(client, bucket: str, prefix: str) -> list[str]:
    """Список ключей объектов с видео-расширениями в префиксе."""
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if key.lower().endswith(VIDEO_EXTENSIONS):
                keys.append(key)
    return keys


def load_processed_state(state_path: str) -> set[str]:
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_processed_state(state_path: str, processed: set):
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(list(processed), f, ensure_ascii=False)


def download_file(client, bucket: str, key: str, local_path: str):
    client.download_file(bucket, key, local_path)


def upload_directory_to_s3(client, bucket: str, prefix: str, local_dir: str):
    """Рекурсивно загружает директорию в S3 под префикс prefix/."""
    local_path = Path(local_dir)
    if not local_path.is_dir():
        return
    prefix = prefix.rstrip("/")
    for f in local_path.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(local_path)
        s3_key = f"{prefix}/{rel.as_posix()}"
        try:
            client.upload_file(str(f), bucket, s3_key)
            logger.info("Upload: %s", s3_key)
        except ClientError as e:
            logger.error("Ошибка загрузки %s: %s", s3_key, e)


def process_one_key(
    client,
    bucket: str,
    key: str,
    config: dict,
    config_minio: dict,
    tmp_dir: str,
) -> bool:
    """Скачать ключ, обработать, выгрузить результат в MinIO. Возвращает True при успехе."""
    input_prefix = (config_minio.get("input_prefix") or "").strip().rstrip("/")
    output_prefix = (config_minio.get("output_prefix") or "spliter_output").strip().rstrip("/")
    local_path = os.path.join(tmp_dir, os.path.basename(key))
    try:
        logger.info("Download: %s -> %s", key, local_path)
        download_file(client, bucket, key, local_path)
    except Exception as e:
        logger.exception("Не удалось скачать %s: %s", key, e)
        return False

    # Конвертация H.265 при необходимости
    if local_path.lower().endswith((".h265", ".hevc")):
        converted = convert_h265_to_video(
            local_path,
            ffmpeg_path=config.get("ffmpeg_path", "ffmpeg"),
            cache_dir=os.path.join(tmp_dir, "cache_h265"),
        )
        if converted:
            local_path = converted
        else:
            logger.warning("Не удалось конвертировать %s, пробуем как есть", key)

    # Временная папка для результата
    out_dir = os.path.join(tmp_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    config_run = {**config, "output_folder": out_dir, "use_video_files": True}

    try:
        extract_frames_for_video((local_path, config_run))
    except Exception as e:
        logger.exception("Ошибка обработки %s: %s", key, e)
        return False

    video_name = safe_video_name(local_path)
    video_out_dir = os.path.join(out_dir, video_name)
    if not os.path.isdir(video_out_dir):
        logger.warning("Папка результата не найдена: %s", video_out_dir)
        return False

    s3_out_prefix = f"{output_prefix}/{video_name}"
    logger.info("Upload результата: %s -> %s", video_out_dir, s3_out_prefix)
    upload_directory_to_s3(client, bucket, s3_out_prefix, video_out_dir)
    return True


def run_once(config: dict, config_minio: dict, state_path: str, processed: set):
    client, endpoint, bucket = get_s3_client(config_minio)
    logger.info("MinIO bucket=%s, input_prefix=%s", bucket, config_minio.get("input_prefix"))
    input_prefix = (config_minio.get("input_prefix") or "").strip().rstrip("/")
    if input_prefix and not input_prefix.endswith("/"):
        input_prefix += "/"
    keys = list_video_keys(client, bucket, input_prefix)
    new_keys = [k for k in keys if k not in processed]
    if not new_keys:
        logger.info("Новых видео нет.")
        return processed
    with tempfile.TemporaryDirectory(prefix="spliter_minio_") as tmp_dir:
        for key in new_keys:
            if process_one_key(client, bucket, key, config, config_minio, tmp_dir):
                processed.add(key)
    return processed


def main():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    config = load_config(config_path)
    config_minio = config.get("minio") or {}
    if not config_minio:
        logger.error(
            "В config.json отсутствует секция 'minio'. "
            "Добавьте: minio: { bucket_name, input_prefix, output_prefix, endpoint_url? }"
        )
        sys.exit(1)
    state_path = config_minio.get("state_file") or "minio_processed.json"
    processed = load_processed_state(state_path)
    once = "--once" in sys.argv
    poll_interval = max(60, int(config_minio.get("poll_interval_sec", 300)))

    if once:
        processed = run_once(config, config_minio, state_path, processed)
        save_processed_state(state_path, processed)
        return

    logger.info("Режим опроса MinIO каждые %s сек. Ctrl+C для выхода.", poll_interval)
    while True:
        try:
            processed = run_once(config, config_minio, state_path, processed)
            save_processed_state(state_path, processed)
        except Exception as e:
            logger.exception("Ошибка цикла: %s", e)
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
