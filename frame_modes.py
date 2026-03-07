import math
import logging

logger = logging.getLogger(__name__)

def get_rare_frame_indices(total_frames, fps):
    """
    Редкий режим:
    - для первого часа: начало, середина, конец
    - для каждого следующего часа: середина, конец
    """
    if total_frames == 0 or fps <= 0:
        return []

    duration_sec = total_frames / fps
    hours = max(1, int(math.ceil(duration_sec / 3600.0)))

    indices = []

    for h in range(hours):
        start_sec = h * 3600.0
        end_sec = min((h + 1) * 3600.0, duration_sec)
        mid_sec = (start_sec + end_sec) / 2.0

        if h == 0:
            start_idx = int(0)
            mid_idx = int(mid_sec * fps)
            end_idx = int(end_sec * fps) - 1
            indices.extend([start_idx, mid_idx, max(end_idx, 0)])
        else:
            mid_idx = int(mid_sec * fps)
            end_idx = int(end_sec * fps) - 1
            indices.extend([mid_idx, max(end_idx, 0)])

    indices = sorted(set(i for i in indices if 0 <= i < total_frames))
    logger.info(f"Редкий режим: выбрано {len(indices)} индексов кадров")
    return indices


def get_frequent_frame_indices(total_frames, fps, interval_sec):
    """
    Частый режим:
    - первый кадр
    - каждые interval_sec
    - последний кадр
    """
    if total_frames == 0 or fps <= 0:
        return []

    duration_sec = total_frames / fps
    indices = [0]

    t = interval_sec
    while t < duration_sec:
        idx = int(t * fps)
        if idx < total_frames:
            indices.append(idx)
        t += interval_sec

    last_idx = total_frames - 1
    indices.append(last_idx)

    indices = sorted(set(i for i in indices if 0 <= i < total_frames))
    logger.info(f"Частый режим: выбрано {len(indices)} индексов кадров")
    return indices
