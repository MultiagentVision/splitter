# Автозапуск spliter при добавлении видео в MinIO

Два варианта: постоянный опрос (polling) или webhook от MinIO.

---

## Вариант 1: Постоянный опрос (без настройки MinIO)

Воркер крутится в фоне и раз в N секунд проверяет папку на MinIO. Новые видео обрабатываются автоматически.

**Запуск в фоне (Ubuntu/WSL):**
```bash
cd /mnt/d/AiChess/spliter3/spliter
nohup ~/.venvs/spliter3/bin/python minio_worker.py > minio_worker.log 2>&1 &
```

**Проверить, что работает:**
```bash
tail -f minio_worker.log
```

**Остановить:**
```bash
pkill -f minio_worker.py
```

В `config.json` в секции `minio` можно уменьшить `poll_interval_sec` (например до 60), чтобы проверять чаще.

**Windows (фоновый запуск):** запустить в отдельном окне PowerShell или через Планировщик заданий (Task Scheduler) задачу с командой:
```
python D:\AiChess\spliter3\spliter\minio_worker.py
```

---

## Вариант 2: Webhook (мгновенный запуск при загрузке)

MinIO при создании объекта отправляет POST на ваш сервер — обработка стартует сразу.

**1. Запустить webhook-сервер** (на машине, до которой MinIO сможет достучаться по HTTP):

```bash
cd /mnt/d/AiChess/spliter3/spliter
~/.venvs/spliter3/bin/python minio_webhook_server.py --port 9000
```

Сервер слушает `http://0.0.0.0:9000/minio-webhook`. Если сервер за NAT, нужен публичный URL (например ngrok: `ngrok http 9000`).

**2. В MinIO настроить уведомление:**

- Открыть консоль MinIO (например https://s3-console.multiagent.vision).
- **Bucket** → **chess-ai** → **Management** → **Event Notifications** (или **Anonymous** → **Event Notifications**).
- **Add Event** (или **Add target**):
  - **Event:** `s3:ObjectCreated:*` (или Put, Post).
  - **Prefix:** `ChessVideoFromCameras/`.
  - **Target:** Webhook.
  - **Endpoint:** `http://<IP_или_домен_вашего_сервера>:9000/minio-webhook`.

После сохранения при загрузке файла в `ChessVideoFromCameras/` MinIO отправит запрос на этот URL и spliter обработает видео автоматически.
