from __future__ import annotations

from typing import Dict, Tuple

from PIL import Image

RoiBox = Tuple[int, int, int, int]

ROI_DEFINITIONS = {
    "name_roi": {
        "x_start": 0.05,
        "x_end": 0.95,
        "y_start": 0.00,
        "y_end": 0.18,
    },
    "bottom_metadata_roi": {
        "x_start": 0.05,
        "x_end": 0.30,
        "y_start": 0.915,
        "y_end": 0.98,
    },
}


def _scale(value: float, size: int) -> int:
    return max(0, min(size, int(round(value * size))))


def roi_boxes_for_size(width: int, height: int) -> Dict[str, RoiBox]:
    if width <= 0 or height <= 0:
        raise ValueError("Image size must be positive.")

    boxes: Dict[str, RoiBox] = {}
    for roi_name, bounds in ROI_DEFINITIONS.items():
        left = _scale(bounds["x_start"], width)
        right = _scale(bounds["x_end"], width)
        top = _scale(bounds["y_start"], height)
        bottom = _scale(bounds["y_end"], height)

        if right <= left:
            right = min(width, left + 1)
        if bottom <= top:
            bottom = min(height, top + 1)

        boxes[roi_name] = (left, top, right, bottom)

    return boxes


def crop_rois(image: Image.Image) -> Dict[str, Image.Image]:
    width, height = image.size
    return {
        roi_name: image.crop(box)
        for roi_name, box in roi_boxes_for_size(width, height).items()
    }
