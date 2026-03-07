import cv2
import numpy as np


def is_frame_corrupted(frame, threshold):
    """
    Быстрая эвристика для определения "битого" кадра.
    Работает на уменьшенной копии кадра, чтобы снизить нагрузку на CPU.
    """
    if frame is None:
        return True

    # Уменьшаем кадр, чтобы последующие операции были дешевле
    # Масштаб подобран как компромисс между скоростью и стабильностью метрики
    h, w = frame.shape[:2]
    scale = 0.25 if max(h, w) > 720 else 0.5
    small = cv2.resize(frame, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # Проверка на рябь (строчные сдвиги) — считаем дифференс только по части строк
    sampled = gray[::2, :]
    diff_rows = float(np.mean(np.abs(np.diff(sampled, axis=0)))) if sampled.shape[0] > 1 else float("nan")
    mean_val = float(np.mean(gray))

    # Для высокого разрешения (4K и выше) diff_rows у нормальных кадров часто 80–100+;
    # порог масштабируем, чтобы избежать ложных срабатываний.
    effective_threshold = threshold * (2.0 if max(h, w) > 1920 else 1.0)

    if not np.isnan(diff_rows) and diff_rows > effective_threshold:
        return True
    if mean_val < 10 or mean_val > 245:
        return True
    return False
