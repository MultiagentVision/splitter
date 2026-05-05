"""
Воркер MinIO: проверка новых файлов (polling), обработка по алгоритму spliter, выгрузка результатов в MinIO.

Использование:
  python minio_worker.py              # цикл опроса (интервал из config)
  python minio_worker.py --once       # один проход
  python minio_worker.py --once --only=Game1.mp4,Game2.mp4   # только эти ключи (по basename или суффиксу)
  python minio_worker.py --once --only=Game1.mp4 --force     # снять с учёта в state_file и обработать снова
  python minio_worker.py --once --no-progress               # без progress bar

В config.json: minio.work_dir — каталог на диске D (скачивание, временные кадры, кеш H.265);
minio.state_file — учёт обработанных ключей (лучше тот же диск).

Остановка: PowerShell .\\stop_minio_worker.ps1 (или taskkill по minio_worker в командной строке).

Cloudflare Access: если CF_* не заданы, воркер ищет токены в
cursor-context-main/secrets/cloudflare-access.env или rules/clearml-training.mdc
(пути рядом с репозиторием или CURSOR_CONTEXT_ROOT).
"""
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from tqdm import tqdm
except ImportError:

    def tqdm(iterable, **kwargs):  # type: ignore[misc,no-redef]
        return iterable

from config_utils import load_config, safe_video_name
from pipeline import extract_frames_for_video
from h265_converter import convert_h265_to_video
from upload_to_s3 import find_aws_credentials, find_working_endpoint


class _FlushStreamHandler(logging.StreamHandler):
    """Сразу сбрасывает буфер — в PowerShell иначе долго не видно прогресс."""

    def emit(self, record):
        super().emit(record)
        self.flush()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[_FlushStreamHandler(sys.stderr)],
    force=True,
)
logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".h265", ".hevc")


def _work_dir_from_config(config_minio: dict) -> str:
    """Локальный диск: скачивание из MinIO, кадры, кеш H.265 (см. minio.work_dir)."""
    wd = (
        (config_minio.get("work_dir") or "").strip()
        or os.getenv("SPLITER_WORK_DIR", "").strip()
        or str(Path(__file__).resolve().parent / "work")
    )
    Path(wd).mkdir(parents=True, exist_ok=True)
    return wd


def _resolve_state_path(state_file: str) -> str:
    """Абсолютный путь к файлу учёта обработанных ключей."""
    p = Path(state_file)
    if p.is_absolute():
        return str(p)
    return str(Path(__file__).resolve().parent / p)


def _parse_only_arg(argv: list[str]) -> list[str] | None:
    for a in argv:
        if a.startswith("--only="):
            parts = [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
            return parts or None
    return None


def _key_matches_only(key: str, patterns: list[str]) -> bool:
    """Совпадение по basename, полному суффиксу ключа или вхождению паттерна в ключ."""
    base = os.path.basename(key)
    for p in patterns:
        if base == p or key == p or key.endswith("/" + p.lstrip("/")) or p in key:
            return True
    return False


def _apply_force_on_processed(processed: set, patterns: list[str] | None) -> None:
    """--force + --only: убрать совпадающие ключи из state, чтобы переработать."""
    if not patterns:
        return
    for k in list(processed):
        if _key_matches_only(k, patterns):
            processed.discard(k)
            logger.info("Снято с учёта (--force): %s", k)

_CF_ENV_KEYS = frozenset(
    {
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "CVAT_CF_ACCESS_CLIENT_ID",
        "CVAT_CF_ACCESS_CLIENT_SECRET",
    }
)


def _parse_simple_env_file(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k in _CF_ENV_KEYS and v:
            os.environ.setdefault(k, v)


def _parse_cf_from_clearml_mdc(path: Path) -> None:
    """Строки вида CF_ACCESS_CLIENT_ID=... в rules/clearml-training.mdc."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        s = raw.strip().lstrip("-").strip().strip("`").strip()
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip().rstrip("`").strip()
        if k in ("CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET") and v:
            os.environ.setdefault(k, v)


def _ensure_cf_env_from_cursor_context() -> None:
    """Подставить CF Access из cursor-context-main, если нет в окружении."""
    cid, csec = _cf_access_tokens()
    if cid and csec:
        return
    spliter_dir = Path(__file__).resolve().parent
    bases: list[Path] = []
    root = os.getenv("CURSOR_CONTEXT_ROOT", "").strip()
    if root:
        bases.append(Path(root))
    bases.extend(
        [
            spliter_dir.parent.parent / "addSplitter" / "cursor-context-main",
            spliter_dir.parent / "cursor-context-main",
            spliter_dir / "cursor-context-main",
        ]
    )
    for base in bases:
        if not base.is_dir():
            continue
        env_p = base / "secrets" / "cloudflare-access.env"
        if env_p.is_file():
            _parse_simple_env_file(env_p)
            cid, csec = _cf_access_tokens()
            if cid and csec:
                logger.info("CF Access: загружено из %s", env_p)
                return
        mdc = base / "rules" / "clearml-training.mdc"
        if mdc.is_file():
            _parse_cf_from_clearml_mdc(mdc)
            cid, csec = _cf_access_tokens()
            if cid and csec:
                logger.info("CF Access: загружено из %s", mdc)
                return


def _cf_access_tokens() -> tuple[str | None, str | None]:
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID") or os.getenv("CVAT_CF_ACCESS_CLIENT_ID")
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET") or os.getenv(
        "CVAT_CF_ACCESS_CLIENT_SECRET"
    )
    return cf_id, cf_secret


def _parse_minio_endpoint(endpoint_url: str) -> tuple[str, bool]:
    if endpoint_url.startswith("https://"):
        p = urlparse(endpoint_url)
        port = p.port or 443
        return f"{p.hostname}:{port}", True
    if endpoint_url.startswith("http://"):
        p = urlparse(endpoint_url)
        port = p.port or 80
        return f"{p.hostname}:{port}", False
    return endpoint_url, os.getenv("MINIO_SECURE", "").lower() in ("1", "true", "yes")


def _endpoint_needs_cloudflare_access(endpoint: str) -> bool:
    """CF service token только для публичного хоста за Access; не для bs3:9000 и т.п."""
    e = (endpoint or "").lower()
    if "multiagent.vision" in e:
        return True
    return False


def _apply_minio_cf_access(client, cf_id: str, cf_secret: str) -> None:
    """CF-заголовки на urllib3 после подписи S3 (как в chessverse train)."""
    from urllib3._collections import HTTPHeaderDict

    orig_http = client._http

    class _CFAccessHTTP:
        def __getattr__(self, name: str):
            return getattr(orig_http, name)

        def urlopen(self, method: str, url: str, **kwargs):
            headers = kwargs.get("headers")
            if headers is None:
                headers = HTTPHeaderDict()
            headers.add("CF-Access-Client-Id", cf_id)
            headers.add("CF-Access-Client-Secret", cf_secret)
            kwargs["headers"] = headers
            return orig_http.urlopen(method, url, **kwargs)

    client._http = _CFAccessHTTP()  # type: ignore[assignment]


class StorageClient:
    """Обёртка над minio SDK (обходит проблемы botocore на Python 3.14+)."""

    def __init__(self, minio_client) -> None:
        self._minio = minio_client

    def list_video_keys(self, bucket: str, prefix: str) -> list[str]:
        keys: list[str] = []
        for obj in self._minio.list_objects(bucket, prefix=prefix, recursive=True):
            name = getattr(obj, "object_name", None) or getattr(obj, "name", None)
            if name and name.lower().endswith(VIDEO_EXTENSIONS):
                keys.append(name)
        return keys

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        self._minio.fget_object(bucket, key, local_path)

    def upload_file(self, local_path: str, bucket: str, key: str) -> None:
        self._minio.fput_object(bucket, key, local_path)


def get_storage_client(config_minio: dict) -> tuple[StorageClient, str, str]:
    """MinIO/S3 через пакет minio; при CF_* — urllib3-обёртка (после подписи)."""
    from minio import Minio

    _ensure_cf_env_from_cursor_context()
    endpoint = config_minio.get("endpoint_url") or os.getenv("S3_ENDPOINT_URL")
    bucket = config_minio.get("bucket_name", "chess-ai")
    access_key, secret_key = find_aws_credentials()
    if not access_key or not secret_key:
        raise RuntimeError(
            "MinIO/S3 credentials не найдены. "
            "Задайте AWS_ACCESS_KEY_ID и AWS_SECRET_ACCESS_KEY или настройте ~/.aws/credentials"
        )
    if not endpoint:
        endpoint = find_working_endpoint(bucket, access_key, secret_key)

    host_port, secure = _parse_minio_endpoint(endpoint)
    # Явный регион: иначе minio делает GetBucketLocation (?location=), который
    # Cloudflare Access часто режет до S3-запроса.
    minio_region = (
        (config_minio.get("region") if isinstance(config_minio.get("region"), str) else None)
        or os.getenv("MINIO_REGION")
        or "us-east-1"
    )
    mc = Minio(
        host_port,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=minio_region,
    )
    cf_id, cf_secret = _cf_access_tokens()
    if cf_id and cf_secret and _endpoint_needs_cloudflare_access(endpoint):
        _apply_minio_cf_access(mc, cf_id, cf_secret)
        logger.info("S3: minio + Cloudflare Access → %s", endpoint)
    else:
        logger.info("S3: minio → %s (TLS=%s, CF=%s)", host_port, secure, False)
    return StorageClient(mc), endpoint, bucket


def list_video_keys(storage: StorageClient, bucket: str, prefix: str) -> list[str]:
    return storage.list_video_keys(bucket, prefix)


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


def upload_directory_to_s3(
    storage: StorageClient,
    bucket: str,
    prefix: str,
    local_dir: str,
    *,
    show_progress: bool = False,
):
    """Рекурсивно загружает директорию в S3 под префикс prefix/."""
    local_path = Path(local_dir)
    if not local_path.is_dir():
        return
    prefix = prefix.rstrip("/")
    files = sorted(f for f in local_path.rglob("*") if f.is_file())
    if not files:
        return
    iterator = files
    if show_progress:
        iterator = tqdm(
            files,
            desc="Upload в MinIO",
            unit="файл",
            mininterval=0.3,
        )
    for f in iterator:
        rel = f.relative_to(local_path)
        s3_key = f"{prefix}/{rel.as_posix()}"
        try:
            storage.upload_file(str(f), bucket, s3_key)
            if not show_progress:
                logger.info("Upload: %s", s3_key)
        except Exception as e:
            logger.error("Ошибка загрузки %s: %s", s3_key, e)


def process_one_key(
    storage: StorageClient,
    bucket: str,
    key: str,
    config: dict,
    config_minio: dict,
    tmp_dir: str,
    *,
    use_progress: bool = True,
) -> bool:
    """Скачать ключ, обработать, выгрузить результат в MinIO. Возвращает True при успехе."""
    t0 = time.perf_counter()
    logger.info(
        "─── Старт: %s | %s ───",
        key,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    input_prefix = (config_minio.get("input_prefix") or "").strip().rstrip("/")
    output_prefix = (config_minio.get("output_prefix") or "spliter_output").strip().rstrip("/")
    local_path = os.path.join(tmp_dir, os.path.basename(key))

    # ── Фаза 1: Download ──────────────────────────────────────────
    t_dl = time.perf_counter()
    try:
        logger.info("[1/4 DOWNLOAD] %s → %s", key, local_path)
        storage.download_file(bucket, key, local_path)
        sz = os.path.getsize(local_path)
        sz_mb = sz / 1024 / 1024
        elapsed_dl = time.perf_counter() - t_dl
        speed = sz_mb / elapsed_dl if elapsed_dl > 0 else 0
        logger.info("[1/4 DOWNLOAD] Готово: %.1f МБ за %.1fs (%.1f МБ/с)", sz_mb, elapsed_dl, speed)
    except Exception as e:
        logger.exception("[1/4 DOWNLOAD] Не удалось скачать %s: %s", key, e)
        logger.info("─── Прервано (download): %s | %.1f мин ───", key, (time.perf_counter() - t0) / 60.0)
        return False

    # ── Фаза 2: Convert ───────────────────────────────────────────
    t_conv = time.perf_counter()
    converted_path = local_path
    if local_path.lower().endswith((".h265", ".hevc")):
        logger.info("[2/4 CONVERT] H.265 → видеофайл: %s", local_path)
        converted = convert_h265_to_video(
            local_path,
            ffmpeg_path=config.get("ffmpeg_path", "ffmpeg"),
            cache_dir=os.path.join(tmp_dir, "cache_h265"),
            strategy=config.get("h265_conversion", "stream_copy"),
        )
        elapsed_conv = time.perf_counter() - t_conv
        if converted:
            conv_sz_mb = os.path.getsize(converted) / 1024 / 1024
            logger.info("[2/4 CONVERT] Готово: %s (%.1f МБ) за %.1fs",
                        os.path.basename(converted), conv_sz_mb, elapsed_conv)
            converted_path = converted
        else:
            logger.warning("[2/4 CONVERT] Не удалось конвертировать за %.1fs, пробуем как есть", elapsed_conv)
    else:
        logger.info("[2/4 CONVERT] Пропущено (не H.265)")
        elapsed_conv = 0.0

    # ── Фаза 3: Extract frames ────────────────────────────────────
    t_extract = time.perf_counter()
    out_dir = os.path.join(tmp_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    config_run = {**config, "output_folder": out_dir, "use_video_files": True}
    if not use_progress:
        config_run["show_progress"] = False

    logger.info("[3/4 EXTRACT] Начало извлечения кадров: %s", converted_path)
    try:
        extract_frames_for_video((converted_path, config_run))
    except Exception as e:
        logger.exception("[3/4 EXTRACT] Ошибка: %s", e)
        logger.info("─── Прервано (extract): %s | %.1f мин ───", key, (time.perf_counter() - t0) / 60.0)
        return False
    elapsed_extract = time.perf_counter() - t_extract
    logger.info("[3/4 EXTRACT] Готово за %.1fs", elapsed_extract)

    video_name = safe_video_name(converted_path)
    video_out_dir = os.path.join(out_dir, video_name)
    if not os.path.isdir(video_out_dir):
        logger.warning("[3/4 EXTRACT] Папка результата не найдена: %s", video_out_dir)
        return False

    # Подсчёт сохранённых файлов
    saved_files = list(Path(video_out_dir).rglob("*.jpg")) + list(Path(video_out_dir).rglob("*.png"))
    logger.info("[3/4 EXTRACT] Сохранено файлов: %d в %s", len(saved_files), video_out_dir)

    # ── Фаза 4: Upload ────────────────────────────────────────────
    t_upload = time.perf_counter()
    s3_out_prefix = f"{output_prefix}/{video_name}"
    logger.info("[4/4 UPLOAD] MinIO s3://%s/%s/…  файлов: %d", bucket, s3_out_prefix, len(saved_files))
    upload_directory_to_s3(
        storage,
        bucket,
        s3_out_prefix,
        video_out_dir,
        show_progress=use_progress,
    )
    elapsed_upload = time.perf_counter() - t_upload
    logger.info("[4/4 UPLOAD] Готово за %.1fs", elapsed_upload)

    elapsed_total = time.perf_counter() - t0
    logger.info(
        "─── Конец: %s | dl=%.1fs conv=%.1fs extract=%.1fs upload=%.1fs total=%.2f мин | %s ───",
        key,
        time.perf_counter() - t_dl - (elapsed_extract + elapsed_upload + elapsed_conv),  # recalc dl
        elapsed_conv if local_path.lower().endswith((".h265", ".hevc")) else 0,
        elapsed_extract,
        elapsed_upload,
        elapsed_total / 60.0,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # ── Cleanup: удаляем скачанный и сконвертированный файлы для экономии места ──
    for cleanup_path in {local_path, converted_path}:
        if cleanup_path and os.path.isfile(cleanup_path):
            try:
                os.remove(cleanup_path)
                logger.info("[CLEANUP] Удалён временный файл: %s", cleanup_path)
            except Exception as e:
                logger.warning("[CLEANUP] Не удалось удалить %s: %s", cleanup_path, e)

    return True


def run_once(
    config: dict,
    config_minio: dict,
    state_path: str,
    processed: set,
    *,
    only_patterns: list[str] | None = None,
    use_progress: bool = True,
):
    storage, endpoint, bucket = get_storage_client(config_minio)
    logger.info("MinIO bucket=%s, input_prefix=%s", bucket, config_minio.get("input_prefix"))
    input_prefix = (config_minio.get("input_prefix") or "").strip().rstrip("/")
    if input_prefix and not input_prefix.endswith("/"):
        input_prefix += "/"
    keys = list_video_keys(storage, bucket, input_prefix)
    if only_patterns:
        keys = [k for k in keys if _key_matches_only(k, only_patterns)]
        logger.info("Фильтр --only=%s → ключей: %s", only_patterns, len(keys))
        if not keys:
            logger.warning("Ни один ключ не подошёл под --only")
            return processed
    new_keys = [k for k in keys if k not in processed]
    if not new_keys:
        logger.info("Новых видео нет.")
        return processed
    work_dir = _work_dir_from_config(config_minio)
    logger.info("Временные файлы и кеш на диске: %s", work_dir)
    with tempfile.TemporaryDirectory(prefix="spliter_minio_", dir=work_dir) as tmp_dir:
        key_iter = new_keys
        if use_progress and len(new_keys) > 1:
            key_iter = tqdm(new_keys, desc="Очередь видео (MinIO)", unit="файл")
        for key in key_iter:
            if process_one_key(
                storage,
                bucket,
                key,
                config,
                config_minio,
                tmp_dir,
                use_progress=use_progress,
            ):
                processed.add(key)
    return processed


def main():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    config = load_config(config_path)
    config_minio = config.get("minio") or {}

    # Env-var overrides (для K8s Job / Docker run без монтирования config.json)
    for env_key, cfg_key in [
        ("FRAME_MODE", "frame_mode"),
        ("QUALITY_LEVEL", "quality_level"),
        ("MINIO_INPUT_PREFIX", "minio.input_prefix"),
        ("MINIO_OUTPUT_PREFIX", "minio.output_prefix"),
    ]:
        val = os.environ.get(env_key, "").strip()
        if val:
            if "." in cfg_key:
                section, key = cfg_key.split(".", 1)
                if section == "minio":
                    config_minio[key] = val
            else:
                config[cfg_key] = val
            logger.info("ENV override: %s=%s", env_key, val)

    if not config_minio:
        logger.error(
            "В config.json отсутствует секция 'minio'. "
            "Добавьте: minio: { bucket_name, input_prefix, output_prefix, endpoint_url? }"
        )
        sys.exit(1)
    if "--no-progress" in sys.argv:
        config["show_progress"] = False
    use_progress = bool(config.get("show_progress", True))

    raw_state = config_minio.get("state_file") or "minio_processed.json"
    state_path = _resolve_state_path(raw_state)
    processed = load_processed_state(state_path)
    once = "--once" in sys.argv
    poll_interval = max(60, int(config_minio.get("poll_interval_sec", 300)))
    only_patterns = _parse_only_arg(sys.argv)
    # ONLY_KEYS env var (K8s Job / Docker run) — comma-separated list of keys
    if not only_patterns:
        env_only = os.environ.get("ONLY_KEYS", "").strip()
        if env_only:
            only_patterns = [x.strip() for x in env_only.split(",") if x.strip()]
            logger.info("ONLY_KEYS (env): %d ключей", len(only_patterns))
    if "--force" in sys.argv and only_patterns:
        _apply_force_on_processed(processed, only_patterns)

    if once:
        logger.info(
            "════════ minio_worker: старт сессии %s ════════",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        logger.info(
            "════════ minio_worker: старт сессии %s ════════",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        t_sess = time.perf_counter()
        processed = run_once(
            config,
            config_minio,
            state_path,
            processed,
            only_patterns=only_patterns,
            use_progress=use_progress,
        )
        save_processed_state(state_path, processed)
        logger.info(
            "════════ финиш сессии %s | длительность %.2f мин ════════",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (time.perf_counter() - t_sess) / 60.0,
        )
        return

    logger.info("Режим опроса MinIO каждые %s сек. Ctrl+C для выхода.", poll_interval)
    while True:
        try:
            processed = run_once(
                config,
                config_minio,
                state_path,
                processed,
                only_patterns=only_patterns,
                use_progress=use_progress,
            )
            save_processed_state(state_path, processed)
        except Exception as e:
            logger.exception("Ошибка цикла: %s", e)
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
