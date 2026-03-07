"""
HTTP-сервер для приёма webhook от MinIO при добавлении новых объектов.
При получении события s3:ObjectCreated запускает обработку видео и выгрузку в MinIO.

Запуск:
  python minio_webhook_server.py [--port 9000]

В MinIO: Event Notifications -> Add target -> Webhook, URL: http://<этот_сервер>:9000/minio-webhook
"""
import json
import logging
import os
import sys
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from config_utils import load_config
from minio_worker import (
    get_s3_client,
    load_processed_state,
    save_processed_state,
    process_one_key,
    VIDEO_EXTENSIONS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def handle_minio_event(bucket: str, key: str):
    """В фоне: обработать один объект и сохранить состояние."""
    try:
        config = load_config(CONFIG_PATH)
        config_minio = config.get("minio") or {}
        if not config_minio:
            logger.error("Секция minio в config.json отсутствует")
            return
        state_path = config_minio.get("state_file") or "minio_processed.json"
        processed = load_processed_state(state_path)
        if key in processed:
            logger.info("Уже обработан: %s", key)
            return
        client, _, _ = get_s3_client(config_minio)
        with tempfile.TemporaryDirectory(prefix="spliter_webhook_") as tmp_dir:
            if process_one_key(client, bucket, key, config, config_minio, tmp_dir):
                processed.add(key)
                save_processed_state(state_path, processed)
    except Exception as e:
        logger.exception("Ошибка обработки %s: %s", key, e)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/minio-webhook" and not path.rstrip("/").endswith("minio-webhook"):
            self.send_response(404)
            self.end_headers()
            return
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
            events = data.get("Events") or [data]
            for ev in events:
                event_name = ev.get("EventName") or ev.get("eventName") or ""
                if "ObjectCreated" not in event_name and "s3:ObjectCreated" not in event_name:
                    continue
                key = ev.get("Key") or ev.get("key") or ""
                bucket = ev.get("Bucket") or ev.get("bucket") or ""
                if not key or not bucket:
                    continue
                if not key.lower().endswith(VIDEO_EXTENSIONS):
                    continue
                logger.info("Webhook: новый объект %s/%s", bucket, key)
                threading.Thread(target=handle_minio_event, args=(bucket, key), daemon=True).start()
        except Exception as e:
            logger.exception("Ошибка разбора webhook: %s", e)

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)


def main():
    port = 9000
    if "--port" in sys.argv:
        i = sys.argv.index("--port")
        if i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    logger.info("Webhook сервер: http://0.0.0.0:%s/minio-webhook (Ctrl+C выход)", port)
    server.serve_forever()


if __name__ == "__main__":
    main()
