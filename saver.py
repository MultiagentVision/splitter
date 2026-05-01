import os
import cv2
import logging

logger = logging.getLogger(__name__)

def save_frame(
    frame,
    base_dir,
    video_name,
    index,
    save_png=True,
    save_jpeg=True,
    *,
    silent: bool = False,
):
    jpeg_dir = os.path.join(base_dir, "jpeg")
    png_dir = os.path.join(base_dir, "png")

    if save_jpeg:
        os.makedirs(jpeg_dir, exist_ok=True)
    if save_png:
        os.makedirs(png_dir, exist_ok=True)

    idx_str = f"{index:05d}"

    if save_jpeg:
        jpg_path = os.path.join(jpeg_dir, f"{video_name}_{idx_str}.jpg")
        cv2.imwrite(jpg_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not silent:
            logger.info("JPEG saved: %s", jpg_path)

    if save_png:
        png_path = os.path.join(png_dir, f"{video_name}_{idx_str}.png")
        cv2.imwrite(png_path, frame)
        if not silent:
            logger.info("PNG saved: %s", png_path)
