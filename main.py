import sys
from logger_setup import setup_logger
from config_utils import load_config
from cli import ask_video_source, ask_user_mode, ask_output_format
from pipeline import run_pipeline


def main():
    """
    Точка входа: чтение конфига, интерактивный выбор режима/источника и запуск пайплайна.
    """
    use_defaults = "--defaults" in sys.argv or len(sys.argv) > 1
    
    config = load_config()

    if not use_defaults:
        config = ask_video_source(config)
        config = ask_user_mode(config)
        config = ask_output_format(config)
    else:
        # Режим по умолчанию: видео файлы, rare режим, medium качество,
        # формат сохранения берётся из config.json (обычно JPEG-only)
        config["use_video_files"] = True
        config["use_stream"] = False
        config["frame_mode"] = "rare"
        config["quality_level"] = "medium"
        print("Используются настройки по умолчанию: видео файлы, rare режим, medium качество")

    setup_logger(config.get("log_level", "INFO"))

    run_pipeline(config)


if __name__ == "__main__":
    main()
