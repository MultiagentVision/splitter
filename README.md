# Spliter3 — Инструкция по использованию

Программа для извлечения кадров из видео с поддержкой локальных файлов, потоков (RTSP, HTTP, YouTube, Google Drive) и автоматической обработки из MinIO.

---

## Содержание

1. [Что делает Spliter3](#1-что-делает-spliter3)
2. [Требования](#2-требования)
3. [Установка](#3-установка)
4. [Быстрый старт](#4-быстрый-старт)
5. [Режимы запуска](#5-режимы-запуска)
6. [Конфигурация](#6-конфигурация)
7. [Источники видео](#7-источники-видео)
8. [Режимы извлечения кадров](#8-режимы-извлечения-кадров)
9. [Работа с MinIO](#9-работа-с-minio)
10. [Загрузка в S3/MinIO](#10-загрузка-в-s3minio)

---

## 1. Что делает Spliter3

- **Извлекает кадры** из видео (MP4, AVI, MOV, MKV, H.265/HEVC)
- **Режимы:** редкий (rare) — один кадр на сцену, или частый (frequent) — кадр каждые N секунд
- **Фильтрация** повреждённых кадров (низкое/среднее/высокое качество)
- **Форматы вывода:** JPEG и/или PNG
- **Источники:** локальная папка, камера, RTSP, HTTP, HLS, YouTube, Google Drive
- **MinIO:** автоматическая проверка новых видео, обработка и выгрузка результатов обратно

---

## 2. Требования

- **Python 3.10+**
- **ffmpeg** (в PATH) — для HEVC/H.265 и потоков
- **Зависимости:** opencv-python, numpy, albumentations, yt_dlp, gdown, boto3

---

## 3. Установка

### Windows

```powershell
cd D:\AiChess\spliter3\spliter
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Ubuntu / WSL

На диске D: (Windows) venv может не работать из‑за прав. Используйте venv в домашней папке Linux:

```bash
cd /mnt/d/AiChess/spliter3/spliter
mkdir -p ~/.venvs
python3 -m venv ~/.venvs/spliter3
~/.venvs/spliter3/bin/pip install -r requirements.txt
```

Запуск (Ubuntu):

```bash
cd /mnt/d/AiChess/spliter3/spliter
~/.venvs/spliter3/bin/python main.py --defaults
```

---

## 4. Быстрый старт

### Локальные видео из папки `videos/`

1. Положите видео (MP4, MKV, AVI и т.д.) в папку `spliter/videos/`
2. Запустите:

```bash
cd spliter
python main.py --defaults
```

Результат появится в папке `output/<имя_видео>/jpeg/` (и/или `png/`).

### Интерактивный режим (выбор источника и настроек)

```bash
python main.py
```

Программа предложит выбрать источник, режим и формат сохранения.

---

## 5. Режимы запуска

| Команда | Описание |
|---------|----------|
| `python main.py` | Интерактивный выбор: источник, режим, формат |
| `python main.py --defaults` | Быстрый запуск: видео из `videos/`, rare, medium, JPEG |

---

## 6. Конфигурация

Файл `config.json` в папке `spliter/`:

| Параметр | Описание |
|----------|----------|
| `input_folder` | Папка с исходными видео (по умолчанию `videos`) |
| `output_folder` | Папка для извлечённых кадров (по умолчанию `output`) |
| `frame_mode` | `rare` или `frequent` |
| `frequent_interval_sec` | Интервал в секундах для режима frequent |
| `quality_level` | `low`, `medium`, `high` — порог фильтрации повреждённых кадров |
| `save_png` / `save_jpeg` | Сохранять PNG и/или JPEG |
| `use_ffmpeg` | Использовать ffmpeg для декодирования (для HEVC — рекомендуется) |
| `processes` | Количество параллельных процессов (0 = авто) |

---

## 7. Источники видео

При интерактивном запуске (`python main.py`) можно выбрать:

1. **Видео из папки** — файлы из `videos/` (и `gdrive_links` из конфига)
2. **Локальная камера** — номер устройства (0, 1, 2...)
3. **URL:**
   - RTSP, HTTP, HLS, MP4
   - YouTube — автоматическое получение прямого потока
   - Google Drive — скачивание в `videos/` и обработка

---

## 8. Режимы извлечения кадров

- **rare** — один «редкий» кадр на сцену (алгоритм выбора ключевых кадров)
- **frequent** — кадр каждые N секунд (`frequent_interval_sec`)

---

## 9. Работа с MinIO

### Настройка

1. Учётные данные в `spliter/.env` или переменные окружения:
   ```
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   ```

2. В `config.json` секция `minio`:
   - `bucket_name`, `input_prefix`, `output_prefix`
   - `endpoint_url` (например `https://s3.multiagent.vision`)

### Вариант A: Постоянный опрос (polling)

Воркер периодически проверяет папку на MinIO и обрабатывает новые видео:

```bash
cd spliter
python minio_worker.py
```

Один проход (без цикла):

```bash
python minio_worker.py --once
```

### Вариант B: Webhook (мгновенный запуск при загрузке)

1. Запустите webhook-сервер:
   ```bash
   python minio_webhook_server.py --port 9000
   ```

2. В MinIO настройте Event Notification → Webhook:
   - URL: `http://<ваш_IP>:9000/minio-webhook`
   - Событие: `s3:ObjectCreated:*`
   - Префикс: `ChessVideoFromCameras/`

Подробнее: `spliter/AUTO_RUN.md`, `spliter/MINIO_README.md`, `spliter/НАСТРОЙКА_MINIO.md`

---

## 10. Загрузка в S3/MinIO

Загрузка локальной папки в S3:

```bash
cd spliter
python upload_to_s3.py
```

Или через PowerShell-скрипт `upload_to_s3.ps1`. Credentials — из `.env`, переменных окружения или `~/.aws/credentials`.

---

## Структура проекта

```
spliter3/
├── README.md                 # Эта инструкция
├── spliter/
│   ├── main.py               # Точка входа (локальные видео, потоки)
│   ├── minio_worker.py       # Воркер MinIO (polling)
│   ├── minio_webhook_server.py # Webhook-сервер для MinIO
│   ├── config.json           # Конфигурация
│   ├── requirements.txt      # Зависимости Python
│   ├── .env                  # Учётные данные (не коммитить)
│   ├── videos/               # Папка с исходными видео
│   ├── output/               # Результаты (кадры)
│   ├── AUTO_RUN.md           # Автозапуск при новых видео
│   ├── MINIO_README.md       # MinIO интеграция
│   └── НАСТРОЙКА_MINIO.md    # Подключение к MinIO
```

---

## Частые вопросы

**Q: Ошибка `No module named 'cv2'`**  
A: Установите зависимости: `pip install -r requirements.txt` (в venv).

**Q: Ошибка `externally-managed-environment`**  
A: Используйте venv (см. раздел «Установка»).

**Q: Ошибка `Operation not permitted` при установке в папку на D:**  
A: Создайте venv в домашней папке Linux: `~/.venvs/spliter3`.

**Q: MinIO credentials не найдены**  
A: Создайте `spliter/.env` с `AWS_ACCESS_KEY_ID` и `AWS_SECRET_ACCESS_KEY` или задайте переменные окружения.
