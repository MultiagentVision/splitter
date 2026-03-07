from typing import Dict, Any, List

from video_sources import (
    detect_url_type,
    get_youtube_stream_url,
    check_stream_available,
    download_gdrive_videos,
)


def ask_video_source(config: Dict[str, Any]) -> Dict[str, Any]:
    print("\n==============================")
    print("   ВЫБОР ИСТОЧНИКА ВИДЕО")
    print("==============================")
    print("1 - Видео из папки videos/")
    print("2 - Локальная камера (0, 1, 2...)")
    print("3 - Вставить URL (RTSP / HTTP / HLS / MP4 / YouTube / Google Drive)")
    choice = input("Введите номер: ").strip()

    if choice == "1":
        config["use_video_files"] = True
        config["use_stream"] = False
        return config

    if choice == "2":
        cam = input("Введите номер камеры (обычно 0): ").strip()
        config["use_video_files"] = False
        config["use_stream"] = True
        config["stream_source"] = int(cam)
        return config

    if choice == "3":
        url = input("Вставьте URL: ").strip()
        url_type = detect_url_type(url)
        print(f"Обнаружен тип источника: {url_type}")

        # YouTube
        if url_type == "youtube":
            print("YouTube обнаружен -> получаю прямой поток...")
            direct_url = get_youtube_stream_url(url)
            config["use_video_files"] = False
            config["use_stream"] = True
            config["stream_source"] = direct_url
            config["use_ffmpeg"] = True
            print("Готово: прямой поток получен.")
            print("Пропускаю проверку доступности для YouTube.")
            return config

        # Google Drive (.h265/.hevc или другие контейнеры)
        if url_type == "gdrive":
            print("Обнаружена ссылка Google Drive, скачиваю видео в папку videos/...")
            download_dir = config.get("input_folder", "videos")
            local_paths: List[str] = download_gdrive_videos([url], download_dir=download_dir)
            if not local_paths:
                print("Не удалось скачать файл с Google Drive.")
                return config

            # Сохраняем их для последующей обработки как обычных видеофайлов
            config.setdefault("extra_video_files", [])
            config["extra_video_files"].extend(local_paths)
            config["use_video_files"] = True
            config["use_stream"] = False
            return config

        # Обычный поток/файл по URL
        config["use_video_files"] = False
        config["use_stream"] = True
        config["stream_source"] = url

        if not check_stream_available(url):
            print("Источник недоступен. Завершение.")
            raise SystemExit(1)

        return config

    print("Неверный выбор. Использую файлы.")
    config["use_video_files"] = True
    config["use_stream"] = False
    return config


def ask_user_mode(config: Dict[str, Any]) -> Dict[str, Any]:
    print("\n==============================")
    print("   ВЫБОР РЕЖИМА ОБРАБОТКИ")
    print("==============================")
    print("1 - редкий (rare)")
    print("2 - частый (frequent)")
    mode = input("Введите номер режима: ").strip()

    if mode == "1":
        config["frame_mode"] = "rare"
    elif mode == "2":
        config["frame_mode"] = "frequent"
        interval = input("Введите интервал в секундах: ").strip()
        try:
            config["frequent_interval_sec"] = int(interval)
        except Exception:
            config["frequent_interval_sec"] = 30
    else:
        config["frame_mode"] = "frequent"

    print("\n==============================")
    print("   ВЫБОР КАЧЕСТВА ФИЛЬТРАЦИИ")
    print("==============================")
    print("1 - низкое")
    print("2 - среднее")
    print("3 - высокое")
    q = input("Введите номер качества: ").strip()

    if q == "1":
        config["quality_level"] = "low"
    elif q == "2":
        config["quality_level"] = "medium"
    elif q == "3":
        config["quality_level"] = "high"
    else:
        config["quality_level"] = "medium"

    return config


def ask_output_format(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выбор формата сохранения кадров:
    1 - только PNG
    2 - только JPEG
    3 - PNG + JPEG
    """
    print("\n==============================")
    print("   ВЫБОР ФОРМАТА СОХРАНЕНИЯ")
    print("==============================")
    print("1 - только PNG")
    print("2 - только JPEG")
    print("3 - PNG + JPEG")
    fmt = input("Введите номер формата: ").strip()

    if fmt == "1":
        config["save_png"] = True
        config["save_jpeg"] = False
    elif fmt == "2":
        config["save_png"] = False
        config["save_jpeg"] = True
    elif fmt == "3":
        config["save_png"] = True
        config["save_jpeg"] = True
    else:
        # если пользователь ввёл мусор — оставляем значения из config.json
        print("Неверный выбор формата, использую значения из конфига.")

    return config

