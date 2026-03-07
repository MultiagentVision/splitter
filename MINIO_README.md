# Обработка видео из MinIO

Проверка появления новых файлов в MinIO, обработка по алгоритму spliter и выгрузка результатов обратно в MinIO.

## Что нужно

1. **Учётные данные MinIO/S3**  
   Один из вариантов:
   - переменные окружения: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`;
   - или файл `~/.aws/credentials` (секция `[default]`).

2. **Секция `minio` в `config.json`** (уже добавлена по умолчанию):

```json
"minio": {
  "bucket_name": "chess-ai",
  "input_prefix": "ChessVideoFromCameras",
  "output_prefix": "spliter_output",
  "endpoint_url": "",
  "poll_interval_sec": 300,
  "state_file": "minio_processed.json"
}
```

- **bucket_name** — бакет MinIO.
- **input_prefix** — префикс (папка), где лежат входящие видео; обрабатываются только новые объекты.
- **output_prefix** — префикс, куда выгружаются кадры после обработки (структура: `output_prefix/<имя_видео>/jpeg/`, `.../png/`).
- **endpoint_url** — URL MinIO (например `https://s3.multiagent.vision`). Если пусто — подставляется из `S3_ENDPOINT_URL` или подбор по уже используемым в проекте endpoint’ам.
- **poll_interval_sec** — интервал опроса (секунды).
- **state_file** — локальный файл со списком уже обработанных ключей (чтобы не обрабатывать одно и то же повторно).

## Режим polling (рекомендуется)

Фоновый цикл: периодически список объектов в MinIO по `input_prefix`, для каждого **нового** видео — скачивание, обработка, выгрузка результата в MinIO.

```bash
# Непрерывный опрос (интервал из config)
python minio_worker.py

# Один проход (проверить новые и выйти)
python minio_worker.py --once
```

Логика:

1. Список ключей в `bucket_name` с префиксом `input_prefix` (расширения: mp4, avi, mov, mkv, h265, hevc).
2. Исключаются ключи из `state_file` (уже обработанные).
3. Для каждого нового ключа:
   - скачивание во временную папку;
   - при необходимости конвертация H.265 → видео;
   - запуск пайплайна spliter (те же параметры, что в `config.json`: frame_mode, quality_level и т.д.);
   - загрузка папки с кадрами (jpeg/png) в MinIO под `output_prefix/<имя_видео>/`.
4. Обработанные ключи дописываются в `state_file`.

## Вариант с webhook’ами MinIO

MinIO умеет слать события (например, при создании объекта) на HTTP endpoint. Тогда можно не опрашивать бакет, а получать уведомления и обрабатывать только их.

Что нужно:

1. **Публичный или доступный из сети MinIO URL** для вызова вашего сервиса (например, `https://your-server/minio-webhook`).
2. **Настройка в MinIO** (через Console или mc):
   - Event Notifications → Add target → Webhook;
   - URL: ваш endpoint;
   - События: например `s3:ObjectCreated:*` для префикса `input_prefix`.
3. **Сервис, принимающий POST** от MinIO и вызывающий обработку одного объекта (bucket + key).

Формат тела webhook у MinIO — JSON с полями вроде `EventName`, `Key`, `Bucket` (зависит от версии MinIO). Минимальная реализация: небольшой HTTP-сервер (Flask/FastAPI), который по приходу события вызывает ту же логику, что и в `minio_worker.py` для одного ключа (скачать → обработать → выгрузить в `output_prefix`), без изменения основного алгоритма spliter.

Итого: для старта достаточно **polling** (`python minio_worker.py` или `--once`); при необходимости позже можно добавить отдельный скрипт/сервис под webhook, который будет использовать те же функции обработки и выгрузки.
