"""
Скрипт для загрузки файлов из локальной папки в S3 bucket.
"""
import os
import sys
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
import logging
import configparser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def _load_dotenv():
    """Загружает .env из папки spliter в os.environ (если файл есть)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k:
                        os.environ.setdefault(k, v)
    except Exception:
        pass


def find_aws_credentials():
    """
    Автоматически ищет AWS credentials в стандартных местах.
    Сначала загружает .env из папки spliter, затем env, затем ~/.aws/credentials.
    Возвращает (access_key_id, secret_access_key) или (None, None).
    """
    _load_dotenv()
    # Переменные окружения (в т.ч. из .env)
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    
    if access_key and secret_key:
        logger.info("Найдены credentials в переменных окружения")
        return access_key, secret_key
    
    # Пробуем найти в ~/.aws/credentials
    aws_dir = Path.home() / ".aws"
    credentials_file = aws_dir / "credentials"
    
    if credentials_file.exists():
        try:
            config = configparser.ConfigParser()
            config.read(credentials_file)
            
            # Пробуем секцию [default]
            if "default" in config:
                access_key = config.get("default", "aws_access_key_id", fallback=None)
                secret_key = config.get("default", "aws_secret_access_key", fallback=None)
                
                if access_key and secret_key:
                    logger.info("Найдены credentials в ~/.aws/credentials")
                    return access_key, secret_key
        except Exception as e:
            logger.debug(f"Ошибка при чтении credentials файла: {e}")
    
    # Пробуем использовать boto3 session (он сам найдет credentials)
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials:
            logger.info("Найдены credentials через boto3.Session()")
            return credentials.access_key, credentials.secret_key
    except Exception as e:
        logger.debug(f"Ошибка при получении credentials через session: {e}")
    
    return None, None


def test_endpoint(endpoint_url, bucket_name, access_key, secret_key):
    """
    Тестирует подключение к S3 endpoint.
    """
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        # Пробуем выполнить простую операцию (list buckets или head bucket)
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except Exception as e:
        logger.debug(f"Endpoint {endpoint_url} не работает: {e}")
        return False


def find_working_endpoint(bucket_name, access_key, secret_key):
    """
    Пробует найти рабочий endpoint из списка возможных вариантов.
    """
    possible_endpoints = [
        "https://s3.multiagent.vision",
        "https://s3-console.multiagent.vision",
        "https://multiagent.vision",
        "https://s3.amazonaws.com",  # стандартный AWS endpoint (на случай если это обычный S3)
    ]
    
    for endpoint in possible_endpoints:
        logger.info(f"Проверка endpoint: {endpoint}")
        if test_endpoint(endpoint, bucket_name, access_key, secret_key):
            logger.info(f"✓ Рабочий endpoint найден: {endpoint}")
            return endpoint
    
    # Если ни один не сработал, возвращаем первый как дефолтный
    logger.warning("Не удалось определить рабочий endpoint, используем первый вариант")
    return possible_endpoints[0]


def upload_file_to_s3(
    local_file_path: str,
    bucket_name: str,
    s3_key: str,
    endpoint_url: str = None,
    aws_access_key_id: str = None,
    aws_secret_access_key: str = None
):
    """
    Загружает один файл в S3.
    
    Args:
        local_file_path: Путь к локальному файлу
        bucket_name: Имя S3 bucket
        s3_key: Ключ (путь) в S3 bucket
        endpoint_url: Кастомный endpoint URL для S3
        aws_access_key_id: AWS Access Key ID
        aws_secret_access_key: AWS Secret Access Key
    """
    try:
        # Создаем S3 клиент
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        
        # Загружаем файл
        file_size = os.path.getsize(local_file_path)
        logger.info(f"Загрузка {os.path.basename(local_file_path)} ({file_size / (1024*1024):.2f} MB)...")
        
        s3_client.upload_file(
            local_file_path,
            bucket_name,
            s3_key,
            Callback=ProgressPercentage(local_file_path, file_size)
        )
        
        logger.info(f"✓ Успешно загружен: {s3_key}")
        return True
        
    except FileNotFoundError:
        logger.error(f"Файл не найден: {local_file_path}")
        return False
    except NoCredentialsError:
        logger.error("AWS credentials не найдены. Проверьте настройки.")
        return False
    except ClientError as e:
        logger.error(f"Ошибка при загрузке {local_file_path}: {e}")
        return False


class ProgressPercentage:
    """Класс для отображения прогресса загрузки."""
    def __init__(self, filename, size):
        self._filename = filename
        self._size = size
        self._seen_so_far = 0
        
    def __call__(self, bytes_amount):
        self._seen_so_far += bytes_amount
        percentage = (self._seen_so_far / self._size) * 100
        print(f"\r{os.path.basename(self._filename)}: {percentage:.1f}%", end='', flush=True)


def upload_directory_to_s3(
    local_dir: str,
    bucket_name: str,
    s3_prefix: str,
    endpoint_url: str = None,
    aws_access_key_id: str = None,
    aws_secret_access_key: str = None
):
    """
    Загружает все файлы из директории в S3.
    
    Args:
        local_dir: Локальная директория с файлами
        bucket_name: Имя S3 bucket
        s3_prefix: Префикс (путь) в S3 bucket
        endpoint_url: Кастомный endpoint URL для S3
        aws_access_key_id: AWS Access Key ID
        aws_secret_access_key: AWS Secret Access Key
    """
    local_path = Path(local_dir)
    
    if not local_path.exists():
        logger.error(f"Директория не существует: {local_dir}")
        return
    
    if not local_path.is_dir():
        logger.error(f"Путь не является директорией: {local_dir}")
        return
    
    # Получаем список всех файлов
    files = [f for f in local_path.iterdir() if f.is_file()]
    
    if not files:
        logger.warning(f"В директории {local_dir} нет файлов")
        return
    
    logger.info(f"Найдено файлов для загрузки: {len(files)}")
    logger.info(f"Bucket: {bucket_name}, Prefix: {s3_prefix}")
    
    # Нормализуем префикс (убираем лишние слэши)
    s3_prefix = s3_prefix.rstrip('/')
    if s3_prefix and not s3_prefix.endswith('/'):
        s3_prefix += '/'
    
    success_count = 0
    failed_count = 0
    
    for file_path in files:
        # Формируем S3 ключ
        s3_key = f"{s3_prefix}{file_path.name}"
        
        if upload_file_to_s3(
            str(file_path),
            bucket_name,
            s3_key,
            endpoint_url,
            aws_access_key_id,
            aws_secret_access_key
        ):
            success_count += 1
        else:
            failed_count += 1
        print()  # Новая строка после прогресса
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Загрузка завершена:")
    logger.info(f"  Успешно: {success_count}")
    logger.info(f"  Ошибок: {failed_count}")
    logger.info(f"{'='*50}")


def main():
    """Основная функция."""
    # Параметры из URL: https://s3-console.multiagent.vision/browser/chess-ai/ChessVideoFromCameras%2F
    LOCAL_DIR = r"D:\AiChess\RehpovotVideo\Rehovot"
    BUCKET_NAME = "chess-ai"
    S3_PREFIX = "ChessVideoFromCameras/"
    
    logger.info("Поиск AWS credentials...")
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY = find_aws_credentials()
    
    # Если credentials не найдены автоматически
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.warning("AWS credentials не найдены автоматически.")
        
        # Проверяем, доступен ли интерактивный ввод
        is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
        
        if is_interactive:
            logger.info("Пожалуйста, введите credentials для доступа к S3:")
            try:
                if not AWS_ACCESS_KEY_ID:
                    AWS_ACCESS_KEY_ID = input("AWS Access Key ID: ").strip()
                if not AWS_SECRET_ACCESS_KEY:
                    AWS_SECRET_ACCESS_KEY = input("AWS Secret Access Key: ").strip()
            except (EOFError, KeyboardInterrupt):
                logger.error("Прервано пользователем")
                return
        else:
            logger.error("Credentials не найдены и интерактивный ввод недоступен.")
            logger.error("Установите переменные окружения:")
            logger.error("  set AWS_ACCESS_KEY_ID=your_access_key")
            logger.error("  set AWS_SECRET_ACCESS_KEY=your_secret_key")
            logger.error("Или создайте файл ~/.aws/credentials с содержимым:")
            logger.error("  [default]")
            logger.error("  aws_access_key_id = your_access_key")
            logger.error("  aws_secret_access_key = your_secret_key")
            return
        
        if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
            logger.error("Credentials обязательны для загрузки файлов!")
            return
    
    # Определяем endpoint
    ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
    if not ENDPOINT_URL:
        logger.info("Поиск рабочего endpoint...")
        ENDPOINT_URL = find_working_endpoint(BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    else:
        logger.info(f"Используется endpoint из переменной окружения: {ENDPOINT_URL}")
    
    logger.info("Начало загрузки файлов в S3")
    logger.info(f"Локальная директория: {LOCAL_DIR}")
    logger.info(f"S3 Bucket: {BUCKET_NAME}")
    logger.info(f"S3 Prefix: {S3_PREFIX}")
    logger.info(f"Endpoint: {ENDPOINT_URL}")
    
    upload_directory_to_s3(
        LOCAL_DIR,
        BUCKET_NAME,
        S3_PREFIX,
        ENDPOINT_URL,
        AWS_ACCESS_KEY_ID,
        AWS_SECRET_ACCESS_KEY
    )


if __name__ == "__main__":
    main()
