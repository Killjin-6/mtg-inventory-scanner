from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


CARD_RATIO = 63.0 / 88.0


def order_points(points: np.ndarray) -> np.ndarray:
    """Return points ordered as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)

    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(-1)

    top_left = pts[np.argmin(sums)]
    bottom_right = pts[np.argmax(sums)]
    top_right = pts[np.argmin(diffs)]
    bottom_left = pts[np.argmax(diffs)]

    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def rectify_card(frame: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Warp a detected card into a flat rectangle."""
    rect = order_points(corners)

    width_top = np.linalg.norm(rect[1] - rect[0])
    width_bottom = np.linalg.norm(rect[2] - rect[3])
    height_right = np.linalg.norm(rect[2] - rect[1])
    height_left = np.linalg.norm(rect[3] - rect[0])

    observed_width = max(width_top, width_bottom)
    observed_height = max(height_left, height_right)

    if observed_width <= observed_height:
        target_height = int(round(max(observed_height, observed_width / CARD_RATIO)))
        target_width = int(round(target_height * CARD_RATIO))
    else:
        target_width = int(round(max(observed_width, observed_height / CARD_RATIO)))
        target_height = int(round(target_width * CARD_RATIO))

    destination = np.array(
        [
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(frame, matrix, (target_width, target_height))


def save_scan(image: np.ndarray, prefix: str, output_dir: str | Path = "data/scans") -> Path:
    """Save an image with a timestamped scan filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{prefix}_{timestamp}.jpg"

    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Failed to save image to {path}.")

    return path
