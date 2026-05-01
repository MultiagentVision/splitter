import albumentations as A
import cv2
import logging

logger = logging.getLogger(__name__)

def build_augmentations(cfg):
    """Аугментации только при albumentations.enable=true (по умолчанию выключены)."""
    cfg = cfg or {}
    if not cfg.get("enable", False):
        logger.info("Albumentations отключены (кадры без изменений)")
        return None

    prob_noise = cfg.get("prob_noise", 0.5)
    prob_bc = cfg.get("prob_brightness_contrast", 0.7)
    prob_rotate = cfg.get("prob_rotate", 0.5)

    transform = A.Compose([
        A.GaussNoise(p=prob_noise),
        A.RandomBrightnessContrast(p=prob_bc),
        A.Rotate(limit=20, border_mode=cv2.BORDER_REFLECT_101, p=prob_rotate),
    ])

    logger.info("Pypeline of Albumentations created")
    return transform

def apply_augmentations(frame, transform):
    if transform is None:
        return frame
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    augmented = transform(image=frame_rgb)["image"]
    return cv2.cvtColor(augmented, cv2.COLOR_RGB2BGR)
