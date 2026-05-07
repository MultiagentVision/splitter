import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Глобальный порог noisy_row_frac. Можно переопределить из pipeline.py через
# frame_quality.NOISY_ROW_FRAC_MAX = N перед запуском обработки.
# 0.15 — стандарт (raw H.265 decode artifacts).
# 1.0 — отключить проверку (interlaced surveillance camera, libx264).
NOISY_ROW_FRAC_MAX: float = 0.15


def is_frame_corrupted(frame, threshold, *, verbose: bool = False,
                       noisy_row_frac_max: float | None = None):
    """
    Эвристика для определения "битого" кадра.
    Работает на уменьшенной копии кадра, чтобы снизить нагрузку на CPU.

    Обнаруживает:
    - рябь / строчные артефакты (high diff_rows)
    - почти чёрный или почти белый кадр
    - однотонный кадр (серый, зелёный и т.п. - H.265 decode artifacts)
    - высокую долю "шумных" строк (частичный decode garbage)

    noisy_row_frac_max: порог для доли зашумлённых строк.
        None — использовать глобальный NOISY_ROW_FRAC_MAX (по умолчанию 0.15).
        1.0 — отключить (interlaced surveillance camera, libx264).
    """
    if noisy_row_frac_max is None:
        noisy_row_frac_max = NOISY_ROW_FRAC_MAX
    if frame is None:
        if verbose:
            logger.debug("is_frame_corrupted: frame is None → True")
        return True

    h, w = frame.shape[:2]
    scale = 0.25 if max(h, w) > 720 else 0.5
    small = cv2.resize(frame, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # Строчные артефакты
    sampled = gray[::2, :]
    if sampled.shape[0] > 1:
        row_diffs = np.abs(np.diff(sampled, axis=0))
        diff_rows = float(np.mean(row_diffs))
        # Доля строк с высоким diff (>= threshold) — для partial-garbage кадров
        noisy_row_frac = float(np.mean(np.mean(row_diffs, axis=1) >= threshold))
    else:
        diff_rows = float("nan")
        noisy_row_frac = 0.0

    mean_val = float(np.mean(gray))

    effective_threshold = threshold * (2.0 if max(h, w) > 1920 else 1.0)

    # Однотонный кадр (серый uninitialized, зелёный YUV artifact):
    # стандартное отклонение каждого BGR-канала мало
    b, g, r = cv2.split(small)
    ch_std = float(np.max([np.std(b), np.std(g), np.std(r)]))
    # Доля "нестандартных" пикселей по зелёному каналу
    # (для зелёного экрана: G >> B и G >> R для большинства пикселей)
    green_dominant = float(np.mean((g.astype(np.int16) - b.astype(np.int16) > 40) &
                                   (g.astype(np.int16) - r.astype(np.int16) > 40)))

    reason = None
    corrupted = False

    if not np.isnan(diff_rows) and diff_rows > effective_threshold:
        corrupted = True
        reason = f"diff_rows={diff_rows:.1f} > {effective_threshold:.1f}"
    elif noisy_row_frac > noisy_row_frac_max:
        corrupted = True
        reason = f"noisy_row_frac={noisy_row_frac:.2f} > {noisy_row_frac_max:.2f}"    elif mean_val < 10 or mean_val > 245:
        corrupted = True
        reason = f"mean_val={mean_val:.1f} (near black/white)"
    elif ch_std < 6.0:
        corrupted = True
        reason = f"ch_std={ch_std:.2f} < 6 (однотонный кадр: серый/цветной артефакт)"
    elif green_dominant > 0.50:
        corrupted = True
        reason = f"green_dominant={green_dominant:.2f} > 0.50 (зелёный экран)"

    if verbose or corrupted:
        logger.debug(
            "frame_quality: %s | diff_rows=%.1f noisy_rows=%.2f mean=%.1f "
            "ch_std=%.2f green_dom=%.2f → %s%s",
            "CORRUPTED" if corrupted else "OK",
            diff_rows if not np.isnan(diff_rows) else -1,
            noisy_row_frac,
            mean_val,
            ch_std,
            green_dominant,
            reason if reason else "OK",
            "",
        )

    return corrupted
