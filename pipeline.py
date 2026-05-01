import os
from multiprocessing import Pool, cpu_count
from typing import Any, Dict, Tuple

import cv2

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):  # type: ignore[misc]
        return iterable
from video_source import VideoSource
from frame_modes import get_rare_frame_indices, get_frequent_frame_indices
from augmentations import build_augmentations, apply_augmentations
from saver import save_frame
from frame_reader import get_frame_seek, get_frame_ffmpeg, get_frame_sequential
from frame_quality import is_frame_corrupted
from config_utils import safe_video_name
from video_sources import get_video_codec, check_stream_available, download_gdrive_videos
from h265_converter import convert_h265_to_video
from video_logger import create_video_logger


def _normalize_video_key(name_or_path: str) -> str:
    """
    Нормализует "ключ видео" так, чтобы:
    - исходный .h265 и его конвертированный *_fixed.mkv считались одним видео;
    - output-папки вида *_fixed_mkv тоже правильно матчились.
    """
    base = os.path.basename(name_or_path)
    stem, _ext = os.path.splitext(base)

    # приводим к нижнему регистру и чистим повторяющиеся суффиксы
    key = stem.lower()

    # убираем повторяющиеся "_fixed"
    while key.endswith("_fixed"):
        key = key[: -len("_fixed")]

    # исторически в output встречались имена типа "*_fixed_mkv"
    if key.endswith("_mkv"):
        key = key[: -len("_mkv")]
    if key.endswith("_mp4"):
        key = key[: -len("_mp4")]

    # ещё раз убираем "_fixed" после среза контейнера
    while key.endswith("_fixed"):
        key = key[: -len("_fixed")]

    return key


def _dir_has_any_files(path: str) -> bool:
    try:
        return any(entry.is_file() for entry in os.scandir(path))
    except Exception:
        return False


def _build_processed_keys(output_root: str) -> set[str]:
    """
    Сканирует output и собирает ключи видео, у которых уже есть хоть 1 кадр
    (jpeg или png).
    """
    processed: set[str] = set()

    if not os.path.isdir(output_root):
        return processed

    for entry in os.scandir(output_root):
        if not entry.is_dir():
            continue

        base_dir = entry.path
        jpeg_dir = os.path.join(base_dir, "jpeg")
        png_dir = os.path.join(base_dir, "png")

        if _dir_has_any_files(jpeg_dir) or _dir_has_any_files(png_dir):
            processed.add(_normalize_video_key(entry.name))

    return processed


def find_next_good_frame(
    start_idx: int,
    current_idx: int,
    vs: VideoSource,
    fps: float,
    threshold: float,
    use_ffmpeg: bool,
    use_seek: bool,
    ffmpeg_path: str,
    video_path: str,
) -> Tuple[Any, Any, int]:
    """
    Поиск следующего неповреждённого кадра, начиная с start_idx.
    Логика перенесена из main.py без изменений.
    """
    idx = start_idx

    while True:
        if use_ffmpeg:
            retX, frameX = get_frame_ffmpeg(video_path, idx, fps, ffmpeg_path)
        elif use_seek:
            retX, frameX = get_frame_seek(vs.cap, idx)
        else:
            if idx == current_idx:
                retX, frameX = True, vs.last_frame
            elif idx > current_idx:
                while current_idx < idx:
                    ret_tmp, frame_tmp = vs.read()
                    if not ret_tmp:
                        return None, None, idx
                    current_idx += 1
                retX, frameX = True, frame_tmp
            else:
                return None, None, idx

        if not retX or frameX is None:
            return None, None, idx

        if not is_frame_corrupted(frameX, threshold):
            return True, frameX, idx

        idx += 1


def find_prev_good_frame(
    start_idx: int,
    vs: VideoSource,
    fps: float,
    threshold: float,
    use_ffmpeg: bool,
    ffmpeg_path: str,
    video_path: str,
    max_search: int = 300,
) -> Tuple[Any, Any, int]:
    """
    Поиск предыдущего читаемого и неповреждённого кадра, отматывая назад от start_idx.
    Используется когда целевой кадр (напр. последний) не удаётся прочитать.
    max_search — максимальное количество шагов назад.
    """
    idx = start_idx
    steps = 0
    while idx >= 0 and steps < max_search:
        if use_ffmpeg:
            retX, frameX = get_frame_ffmpeg(video_path, idx, fps, ffmpeg_path)
        else:
            retX, frameX = get_frame_seek(vs.cap, idx)

        if retX and frameX is not None and not is_frame_corrupted(frameX, threshold):
            return True, frameX, idx

        idx -= 1
        steps += 1

    return None, None, start_idx


def extract_frames_for_video(args):
    """
    Обработка одного видеофайла или потока.
    Логика перенесена из main.py, слегка адаптирована под новый импорт.
    """
    video_path, config = args

    base_path_str = str(video_path)

    use_ffmpeg_cfg = config.get("use_ffmpeg", False)
    ffmpeg_path = config.get("ffmpeg_path", "ffmpeg")

    codec = get_video_codec(base_path_str)

    # Для .h265/.hevc конвертация уже была сделана выше (через convert_h265_to_video),
    # поэтому здесь только включаем ffmpeg по кодеку.
    effective_use_ffmpeg = use_ffmpeg_cfg
    if codec and codec.lower() in ("hevc", "h265"):
        effective_use_ffmpeg = True

    vs = VideoSource(base_path_str, use_ffmpeg=effective_use_ffmpeg, ffmpeg_path=ffmpeg_path)

    fps = vs.get_fps()
    total_frames = vs.get_total_frames()

    output_folder = config["output_folder"]
    video_name = safe_video_name(base_path_str)
    base_dir = os.path.join(output_folder, video_name)
    os.makedirs(base_dir, exist_ok=True)

    logger = create_video_logger(video_name, base_dir)
    logger.info(f"Начало обработки: {base_path_str}")

    if codec:
        logger.info(f"Обнаружен видеокодек: {codec}")
        if codec.lower() in ("hevc", "h265"):
            logger.info("Кодек HEVC/H.265 -> используется ffmpeg.")
    else:
        logger.info("Кодек определить не удалось (ffprobe).")

    if fps <= 0:
        fps = config.get("default_fps", 25)
        logger.info(f"FPS неизвестен, использую default_fps={fps}")

    if total_frames <= 0:
        total_frames = int(fps * 60 * 60 * 24)
        logger.info("Поток: total_frames неизвестно, использую большое значение")

    frame_mode = config.get("frame_mode", "frequent")
    frequent_interval_sec = config.get("frequent_interval_sec", 30)

    if frame_mode == "rare":
        target_indices = get_rare_frame_indices(total_frames, fps)
    else:
        target_indices = get_frequent_frame_indices(total_frames, fps, frequent_interval_sec)

    logger.info(f"Режим={frame_mode}, выбрано индексов={len(target_indices)}")

    transform = build_augmentations(config.get("albumentations", {}))

    save_png = config.get("save_png", True)
    save_jpeg = config.get("save_jpeg", True)

    use_seek = config.get("use_seek", False)
    use_ffmpeg = effective_use_ffmpeg

    quality = config.get("quality_level", "medium")
    thresholds = config.get("quality_thresholds", {"low": 60, "medium": 35, "high": 20})
    threshold = thresholds.get(quality, 35)

    logger.info(f"Качество={quality}, порог={threshold}")
    logger.info(f"Декодер: {'ffmpeg' if use_ffmpeg else 'opencv'}")

    target_set = set(target_indices)
    max_target = max(target_indices) if target_indices else 0
    saved_count = 0

    is_file_mode = config.get("use_video_files", True)

    if is_file_mode:
        # Новый режим: прямой доступ по времени/индексу без последовательного чтения всех кадров.
        logger.info(
            f"Файловый режим: прямой доступ к {len(target_indices)} кадрам "
            f"через {'ffmpeg' if use_ffmpeg else ('seek' if use_seek else 'seek/OpenCV')}"
        )

        show_bar = config.get("show_progress", True) and not os.environ.get(
            "SPLITER_NO_PROGRESS", ""
        )
        frame_silent = show_bar
        idx_sequence = sorted(target_indices)
        if show_bar:
            idx_sequence = tqdm(
                idx_sequence,
                desc=f"Кадры: {video_name[:36]}",
                unit="кадр",
                mininterval=0.5,
                smoothing=0.05,
            )

        for target_idx in idx_sequence:
            # Берём кадр по индексу (индекс -> время: t = target_idx / fps внутри get_frame_ffmpeg)
            if use_ffmpeg:
                ret2, frame2 = get_frame_ffmpeg(base_path_str, target_idx, fps, ffmpeg_path)
            else:
                # Используем seek по номеру кадра (без прокрутки всех предыдущих)
                ret2, frame2 = get_frame_seek(vs.cap, target_idx)

            if not ret2 or frame2 is None:
                logger.warning(f"Не удалось прочитать кадр {target_idx}, ищем предыдущий")
                ret2, frame2, good_idx = find_prev_good_frame(
                    target_idx - 1,
                    vs,
                    fps,
                    threshold,
                    use_ffmpeg,
                    ffmpeg_path,
                    base_path_str,
                )
                if not ret2 or frame2 is None:
                    logger.warning(f"Не найден читаемый кадр перед {target_idx}, пропускаю")
                    continue
                logger.info(f"Использован кадр {good_idx} вместо нечитаемого {target_idx}")

            # Первый и последний кадр сохраняем как есть (без проверки на повреждённость)
            is_first_or_last = target_idx == 0 or target_idx == total_frames - 1
            if not is_first_or_last and is_frame_corrupted(frame2, threshold):
                logger.info(f"Кадр {target_idx} повреждён — ищем следующий")
                # Ищем следующий хороший кадр также прямым доступом
                ret2, frame2, good_idx = find_next_good_frame(
                    target_idx + 1,
                    target_idx,
                    vs,
                    fps,
                    threshold,
                    use_ffmpeg,
                    True,  # для файлового режима используем seek
                    ffmpeg_path,
                    base_path_str,
                )
                if not ret2 or frame2 is None:
                    logger.warning(f"Не найден хороший кадр после {target_idx}")
                    continue
                logger.info(f"Использован кадр {good_idx} вместо {target_idx}")

            aug_frame = apply_augmentations(frame2, transform)
            saved_count += 1
            save_frame(
                aug_frame,
                base_dir=base_dir,
                video_name=video_name,
                index=saved_count,
                save_png=save_png,
                save_jpeg=save_jpeg,
                silent=frame_silent,
            )

        vs.release()
        logger.info(f"Готово (файловый режим): {video_name}, сохранено кадров: {saved_count}")
        return

    # СТАРАЯ ЛОГИКА ПОСЛЕДОВАТЕЛЬНОГО ЧТЕНИЯ ДЛЯ ПОТОКОВ (RTSP/HTTP/YouTube)
    # Оставлена для обратной совместимости, но для файловых видео больше не используется.
    #
    # current_idx = 0
    # ret, frame = vs.read()
    #
    # while True:
    #     if not ret:
    #         logger.warning("Поток оборвался — попытка переподключения...")
    #
    #         if check_stream_available(base_path_str):
    #             vs = VideoSource(base_path_str, use_ffmpeg=use_ffmpeg, ffmpeg_path=ffmpeg_path)
    #             ret, frame = vs.read()
    #             if not ret:
    #                 logger.error("Не удалось восстановить поток.")
    #                 break
    #             logger.info("Поток восстановлен.")
    #         else:
    #             logger.error("Источник недоступен. Завершение.")
    #             break
    #
    #     if current_idx in target_set:
    #         if use_ffmpeg:
    #             ret2, frame2 = get_frame_ffmpeg(base_path_str, current_idx, fps, ffmpeg_path)
    #         elif use_seek:
    #             ret2, frame2 = get_frame_seek(vs.cap, current_idx)
    #         else:
    #             ret2, frame2 = get_frame_sequential(vs.cap, current_idx, current_idx, frame)
    #
    #         if is_frame_corrupted(frame2, threshold):
    #             logger.info(f"Кадр {current_idx} повреждён — ищем следующий")
    #
    #             ret2, frame2, good_idx = find_next_good_frame(
    #                 current_idx + 1,
    #                 current_idx,
    #                 vs,
    #                 fps,
    #                 threshold,
    #                 use_ffmpeg,
    #                 use_seek,
    #                 ffmpeg_path,
    #                 base_path_str,
    #             )
    #
    #             if not ret2:
    #                 logger.warning(f"Не найден хороший кадр после {current_idx}")
    #                 current_idx += 1
    #                 ret, frame = vs.read()
    #                 continue
    #
    #             logger.info(f"Использован кадр {good_idx} вместо {current_idx}")
    #             current_idx = good_idx
    #
    #         aug_frame = apply_augmentations(frame2, transform)
    #
    #         saved_count += 1
    #         save_frame(
    #             aug_frame,
    #             base_dir=base_dir,
    #             video_name=video_name,
    #             index=saved_count,
    #             save_png=save_png,
    #             save_jpeg=save_jpeg,
    #         )
    #
    #     current_idx += 1
    #     if current_idx > max_target:
    #         break
    #
    #     ret, frame = vs.read()

    # Если всё-таки обрабатываем поток, просто закрываем ресурс
    vs.release()
    logger.info(f"Готово (потоковый режим): {video_name}, сохранено кадров: {saved_count}")


def run_pipeline(config: Dict[str, Any]) -> None:
    """
    Высокоуровневая функция запуска пайплайна:
    - работа с файлами;
    - конвертация H.265 через convert_h265_to_video;
    - параллельная обработка видео.
    """
    if config.get("use_video_files", True):
        input_folder = config["input_folder"]

        output_root = config.get("output_folder", "output")
        processed_keys = _build_processed_keys(output_root)

        # Summary-счётчики
        found_local = 0
        downloaded_total = 0
        skipped_processed = 0

        # 1) стандартные файлы из папки
        videos = [
            os.path.join(input_folder, f)
            for f in os.listdir(input_folder)
            if f.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".h265", ".hevc"))
        ]
        found_local = len(videos)

        # 2) ссылки Google Drive из конфига (дополнительно к интерактивным)
        gdrive_links = config.get("gdrive_links") or []
        if gdrive_links:
            downloaded = download_gdrive_videos(gdrive_links, download_dir=input_folder)
            downloaded_total += len(downloaded)
            if downloaded:
                # сразу отсекаем уже обработанные (чтобы не попадали в очередь)
                not_processed = []
                for p in downloaded:
                    if _normalize_video_key(p) in processed_keys:
                        print(f"[SKIP][GDRIVE] Уже обработано: {p}")
                        skipped_processed += 1
                        continue
                    not_processed.append(p)

                if not_processed:
                    config.setdefault("extra_video_files", [])
                    config["extra_video_files"].extend(not_processed)

        # 3) добавляем файлы, скачанные, например, с Google Drive (CLI + config)
        for extra in config.get("extra_video_files", []):
            if extra not in videos:
                videos.append(extra)

        if not videos:
            print("В папке videos нет видеофайлов.")
            return

        # 4) Фильтрация уже обработанных видео:
        #    используем processed_keys, чтобы .h265 и *_fixed.mkv считались одним видео.
        filtered_videos = []
        for v in videos:
            if _normalize_video_key(v) in processed_keys:
                print(f"[SKIP] Уже обработано: {v}")
                skipped_processed += 1
                continue
            filtered_videos.append(v)

        videos = filtered_videos

        if not videos:
            print("Нет новых видео для обработки.")
            return

        # 4.1) Ограничение размера батча
        max_videos_per_run = int(config.get("max_videos_per_run", 0) or 0)
        if max_videos_per_run > 0 and len(videos) > max_videos_per_run:
            # детерминируем порядок
            videos = sorted(videos)[:max_videos_per_run]

        print(
            "\n=== SUMMARY ===\n"
            f"local_found={found_local}\n"
            f"gdrive_downloaded={downloaded_total}\n"
            f"skipped_already_processed={skipped_processed}\n"
            f"selected_for_run={len(videos)}\n"
            f"max_videos_per_run={max_videos_per_run}\n"
            "==============="
        )

        # 5. Авто-конвертация всех .h265/.hevc → нормальное видео
        repaired_videos = []
        for v in videos:
            if v.lower().endswith((".h265", ".hevc")):
                print(f"\n[H265] Обнаружен raw HEVC: {v}")
                converted = convert_h265_to_video(
                    v,
                    ffmpeg_path=config.get("ffmpeg_path", "ffmpeg"),
                    cache_dir="cache_h265",
                )
                if converted:
                    print(f"[H265] Готовое видео: {converted}")
                    repaired_videos.append(converted)
                else:
                    print(f"[H265] Не удалось конвертировать {v}, пропускаю.")
            else:
                repaired_videos.append(v)

        videos = repaired_videos

        if not videos:
            print("Нет видео для обработки после конвертации.")
            return

        # 6. Параллельная обработка
        processes = min(config.get("processes", cpu_count()), len(videos))
        print(f"\nНачинаю обработку {len(videos)} видео(файлов) в {processes} процессах...")

        with Pool(processes=processes) as pool:
            pool.map(extract_frames_for_video, [(v, config) for v in videos])

        print("\nОбработка завершена.")

    else:
        # Обработка потоков (RTSP/HTTP/YouTube)
        source = config["stream_source"]
        extract_frames_for_video((source, config))

