# Подключение к MinIO по адресу multiagent.vision

Нужно: **подключаться к хранилищу**, проверять папку `chess-ai/ChessVideoFromCameras/`, обрабатывать новые видео и загружать кадры обратно в тот же бакет.

---

## 1. Адрес и папка (уже настроено)

- **Веб-консоль (браузер):**  
  https://s3-console.multiagent.vision/browser/chess-ai/ChessVideoFromCameras/

- **API (для скриптов):**  
  `https://s3.multiagent.vision`  
  В `config.json` в секции `minio` уже указано:
  - `bucket_name`: `chess-ai`
  - `input_prefix`: `ChessVideoFromCameras` — откуда берём видео
  - `output_prefix`: `ChessVideoFromCameras` — куда кладём результаты (подпапки `<имя_видео>/jpeg/`, `.../png/`)
  - `endpoint_url`: `https://s3.multiagent.vision`

---

## 2. Что нужно получить и где взять

Для доступа по API нужны **два значения**:

| Что | Где взять |
|-----|-----------|
| **Access Key ID** | Администратор сервера multiagent.vision или тот, кто настраивал MinIO. Либо в веб-консоли MinIO: **Access Keys** / **Service Accounts** → создать ключ. |
| **Secret Access Key** | Выдаётся **один раз** при создании ключа (вместе с Access Key ID). Сохранить в надёжном месте. |

Без этих ключей скрипт не сможет ни читать список файлов, ни скачивать видео, ни загружать кадры обратно.

---

## 3. Куда подставить ключи

**Вариант А — переменные окружения (удобно для запуска вручную или в скрипте):**

В PowerShell (Windows):

```powershell
$env:AWS_ACCESS_KEY_ID = "ваш_access_key_id"
$env:AWS_SECRET_ACCESS_KEY = "ваш_secret_access_key"
```

В Ubuntu (WSL) или Linux, в том же терминале перед запуском:

```bash
export AWS_ACCESS_KEY_ID="ваш_access_key_id"
export AWS_SECRET_ACCESS_KEY="ваш_secret_access_key"
```

**Вариант Б — файл (один раз настроил и не вводишь в консоль):**

Файл (подставь свой путь к папке пользователя):

- Windows: `C:\Users\<ИмяПользователя>\.aws\credentials`
- Linux/WSL: `~/.aws/credentials`

Содержимое:

```ini
[default]
aws_access_key_id = ваш_access_key_id
aws_secret_access_key = ваш_secret_access_key
```

Папку `.aws` создай, если её нет.

---

## 4. Запуск

Из каталога `spliter`, с настроенным venv (или системным Python с зависимостями):

```bash
# Один проход: проверить новые файлы, обработать, выгрузить в ChessVideoFromCameras
python minio_worker.py --once
```

Непрерывный режим (каждые 5 минут проверяет папку):

```bash
python minio_worker.py
```

Логика:

1. Подключение к `https://s3.multiagent.vision`, бакет `chess-ai`, префикс `ChessVideoFromCameras`.
2. Список объектов с расширениями видео (mp4, mkv, avi, mov, h265, hevc).
3. Обработка только тех, которые ещё не были обработаны (список в `minio_processed.json`).
4. Для каждого нового: скачивание → обработка (spliter) → загрузка кадров обратно в `ChessVideoFromCameras/<имя_видео>/jpeg/` и `.../png/`.

---

## 5. Если ключей нет

- Напиши администратору или владельцу сервера **multiagent.vision** и запроси **S3/MinIO Access Key и Secret Key** для бакета `chess-ai` (или для твоего пользователя).
- Если у тебя есть доступ в веб-консоль MinIO — зайди в раздел создания **Access Keys** или **Service Accounts** и создай новый ключ; Secret показывается только при создании.

После того как ключи будут подставлены (переменные окружения или `~/.aws/credentials`), достаточно запускать `python minio_worker.py --once` или `python minio_worker.py` — подключение идёт по адресу `https://s3.multiagent.vision`, папка — `chess-ai/ChessVideoFromCameras/`.
