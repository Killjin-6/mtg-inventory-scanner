from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, Iterable, Tuple

import numpy as np
from PIL import Image

from ocr.rois import crop_rois

try:
    import easyocr
except Exception as exc:  # pragma: no cover - depends on local environment
    easyocr = None
    _EASYOCR_IMPORT_ERROR = exc
else:
    _EASYOCR_IMPORT_ERROR = None

try:
    import torch
except Exception as exc:  # pragma: no cover - depends on local environment
    torch = None
    _TORCH_IMPORT_ERROR = exc
else:
    _TORCH_IMPORT_ERROR = None

OCRValue = Tuple[str, float]
OCRResults = Dict[str, OCRValue]
UNAVAILABLE_MESSAGE = "OCR unavailable on this Python version (torch not installed)."


def ocr_availability_message() -> str | None:
    if torch is None:
        return UNAVAILABLE_MESSAGE
    if easyocr is None:
        return f"OCR unavailable: {type(_EASYOCR_IMPORT_ERROR).__name__}: {_EASYOCR_IMPORT_ERROR}"
    return None


def _should_use_gpu() -> bool:
    if torch is None:
        return False

    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def normalize_set_code(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text).upper()[:8]


class EasyOCRReader:
    def __init__(self, languages: Iterable[str] | None = None, gpu: bool | None = None) -> None:
        availability_error = ocr_availability_message()
        if availability_error is not None:
            raise RuntimeError(availability_error)

        use_gpu = _should_use_gpu() if gpu is None else gpu

        try:
            self._reader = easyocr.Reader(list(languages or ["en"]), gpu=use_gpu)
            self.using_gpu = use_gpu
        except Exception:
            if not use_gpu:
                raise

            self._reader = easyocr.Reader(list(languages or ["en"]), gpu=False)
            self.using_gpu = False

    def read_rois(self, image_path: str | Path) -> OCRResults:
        path = Path(image_path)
        with Image.open(path) as image:
            roi_images = crop_rois(image.convert("RGB"))

        results: OCRResults = {}
        for roi_name, roi_image in roi_images.items():
            text, confidence = self._read_single_roi(roi_image)
            if roi_name == "set_code_roi":
                text = normalize_set_code(text)
            results[roi_name] = (text, confidence)

        return results

    def _read_single_roi(self, roi_image: Image.Image) -> OCRValue:
        entries = self._reader.readtext(np.array(roi_image), detail=1, paragraph=False)
        texts = []
        confidences = []

        for entry in entries:
            if len(entry) < 3:
                continue

            text = str(entry[1]).strip()
            confidence = float(entry[2]) if entry[2] is not None else 0.0
            if not text:
                continue

            texts.append(text)
            confidences.append(max(0.0, min(1.0, confidence)))

        if not texts:
            return ("", 0.0)

        return (" ".join(texts), sum(confidences) / len(confidences))


_READER: EasyOCRReader | None = None


def get_easyocr_reader() -> EasyOCRReader:
    global _READER
    if _READER is None:
        _READER = EasyOCRReader()
    return _READER
