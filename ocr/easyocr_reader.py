from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, Iterable, Tuple

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


def normalize_collector_number(text: str) -> str:
    cleaned = re.sub(r"\s+", "", text)
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[0]
    return re.sub(r"[^A-Za-z0-9]", "", cleaned)[:16]


def normalize_lang(text: str) -> str:
    return re.sub(r"[^A-Za-z]", "", text).upper()[:3]


def parse_bottom_metadata(text: str) -> dict[str, str]:
    compact_text = " ".join(text.strip().split())
    collector_match = re.search(r"([A-Za-z]?\d+[A-Za-z]?)(?:\s*/\s*(\d+))?", compact_text)
    collector_text = ""
    if collector_match:
        collector_text = collector_match.group(0).replace(" ", "")

    rarity_match = re.search(r"\b([CUMRLMS])\b", compact_text.upper())
    rarity = rarity_match.group(1) if rarity_match else ""
    upper_text = compact_text.upper()
    tokens = re.findall(r"[A-Z0-9]+", upper_text)

    set_code = ""
    if collector_match:
        trailing_text = upper_text[collector_match.end() :]
        trailing_tokens = re.findall(r"[A-Z0-9]+", trailing_text)
    else:
        trailing_tokens = tokens

    candidate_tokens = []
    for token in trailing_tokens:
        normalized_token = normalize_set_code(token)
        if not normalized_token:
            continue
        if normalized_token in {rarity, normalize_lang(token)}:
            continue
        if normalized_token == normalize_collector_number(collector_text):
            continue
        if len(normalized_token) > 5:
            continue
        candidate_tokens.append(normalized_token)

    if candidate_tokens:
        set_code = candidate_tokens[0]

    lang_match = re.search(r"\b(EN|ES|FR|DE|IT|PT|JA|KO|RU|ZHS|ZHT)\b", compact_text.upper())
    lang = lang_match.group(1) if lang_match else ""

    if not set_code:
        for token in reversed(tokens):
            normalized_token = normalize_set_code(token)
            if normalized_token in {rarity, lang, normalize_collector_number(collector_text)}:
                continue
            if len(normalized_token) > 5:
                continue
            set_code = normalized_token
            break

    return {
        "printed_collector_text": collector_text,
        "collector_number": normalize_collector_number(collector_text),
        "rarity": rarity,
        "set_code": normalize_set_code(set_code),
        "lang": normalize_lang(lang),
    }


def extract_parsed_metadata(ocr_results: OCRResults) -> dict[str, Any]:
    metadata_text, metadata_confidence = ocr_results.get("bottom_metadata_roi", ("", 0.0))
    parsed = parse_bottom_metadata(metadata_text)
    parsed["bottom_metadata_text"] = metadata_text
    parsed["bottom_metadata_confidence"] = metadata_confidence
    return parsed


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
