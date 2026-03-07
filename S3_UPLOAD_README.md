# Инструкция по загрузке файлов в S3

## Описание

Скрипты для загрузки файлов из папки `D:\AiChess\RehpovotVideo\Rehovot` в S3 bucket `chess-ai` по пути `ChessVideoFromCameras/`.

**Найдено файлов для загрузки:** 23 файла (общий размер ~2 GB)

## Быстрый старт

### Вариант 1: Использование PowerShell скрипта (рекомендуется)

```powershell
cd D:\AiChess\spliter3\spliter
.\upload_to_s3.ps1
```

Скрипт автоматически запросит credentials, если они не установлены.

### Вариант 2: Использование Python скрипта напрямую

```powershell
cd D:\AiChess\spliter3\spliter
python upload_to_s3.py
```

## Настройка AWS Credentials

Для загрузки файлов необходимо настроить AWS credentials одним из способов:

### Способ 1: Переменные окружения (PowerShell)

```powershell
$env:AWS_ACCESS_KEY_ID = "ваш_access_key"
$env:AWS_SECRET_ACCESS_KEY = "ваш_secret_key"
```

### Способ 2: Переменные окружения (CMD)

```cmd
set AWS_ACCESS_KEY_ID=ваш_access_key
set AWS_SECRET_ACCESS_KEY=ваш_secret_key
```

### Способ 3: Файл ~/.aws/credentials

Создайте файл `C:\Users\ВашеИмя\.aws\credentials` с содержимым:

```ini
[default]
aws_access_key_id = ваш_access_key
aws_secret_access_key = ваш_secret_key
```

## Настройка S3 Endpoint (опционально)

По умолчанию скрипт автоматически определяет рабочий endpoint. Если нужно задать вручную:

```powershell
$env:S3_ENDPOINT_URL = "https://s3.multiagent.vision"
```

Возможные варианты endpoint:
- `https://s3.multiagent.vision`
- `https://s3-console.multiagent.vision`
- `https://multiagent.vision`

## Параметры загрузки

- **Локальная папка:** `D:\AiChess\RehpovotVideo\Rehovot`
- **S3 Bucket:** `chess-ai`
- **S3 Prefix:** `ChessVideoFromCameras/`
- **Endpoint:** Автоматически определяется или задается через `S3_ENDPOINT_URL`

## Особенности

- ✅ Автоматический поиск credentials в стандартных местах
- ✅ Автоматическое определение рабочего endpoint
- ✅ Отображение прогресса загрузки для каждого файла
- ✅ Подробное логирование процесса
- ✅ Обработка ошибок и повторные попытки

## Требования

- Python 3.x
- boto3 (установлен через `pip install boto3`)
- AWS credentials с правами на запись в bucket `chess-ai`

## Пример вывода

```
2026-02-21 10:55:18 [INFO] Поиск AWS credentials...
2026-02-21 10:55:18 [INFO] Найдены credentials в переменных окружения
2026-02-21 10:55:18 [INFO] Поиск рабочего endpoint...
2026-02-21 10:55:19 [INFO] Проверка endpoint: https://s3.multiagent.vision
2026-02-21 10:55:20 [INFO] ✓ Рабочий endpoint найден: https://s3.multiagent.vision
2026-02-21 10:55:20 [INFO] Начало загрузки файлов в S3
2026-02-21 10:55:20 [INFO] Найдено файлов для загрузки: 23
2026-02-21 10:55:21 [INFO] Загрузка 1000_01_M_20251222020000.h265 (101.58 MB)...
1000_01_M_20251222020000.h265: 100.0%
2026-02-21 10:55:45 [INFO] ✓ Успешно загружен: ChessVideoFromCameras/1000_01_M_20251222020000.h265
...
```

## Устранение проблем

### Ошибка: "AWS credentials не найдены"

Убедитесь, что credentials установлены одним из способов выше.

### Ошибка: "Endpoint не работает"

Проверьте правильность endpoint URL или задайте его вручную через переменную окружения `S3_ENDPOINT_URL`.

### Ошибка: "Access Denied"

Проверьте, что ваши credentials имеют права на запись в bucket `chess-ai` и путь `ChessVideoFromCameras/`.
