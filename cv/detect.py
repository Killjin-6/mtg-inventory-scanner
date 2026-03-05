from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


class CardDetectionError(RuntimeError):
    """Raised when a likely card contour cannot be found."""


@dataclass(slots=True)
class DetectionResult:
    corners: np.ndarray
    contour: np.ndarray
    area: float


def detect_card(frame: np.ndarray) -> DetectionResult:
    """Detect the dominant card-like quadrilateral in a captured frame."""
    if frame is None or frame.size == 0:
        raise CardDetectionError("No image data was provided for detection.")

    grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    edges = cv2.Canny(blurred, 75, 200)
    edges = cv2.dilate(edges, np.ones((3, 3), dtype=np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise CardDetectionError("No contours were found in the captured image.")

    image_area = frame.shape[0] * frame.shape[1]
    best_result: DetectionResult | None = None

    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < image_area * 0.10:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue

        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue

        points = polygon.reshape(4, 2).astype(np.float32)
        width, height = _edge_lengths(points)
        if width <= 0 or height <= 0:
            continue

        short_edge = min(width, height)
        long_edge = max(width, height)
        edge_ratio = short_edge / long_edge
        if edge_ratio < 0.45 or edge_ratio > 0.85:
            continue

        if best_result is None or area > best_result.area:
            best_result = DetectionResult(corners=points, contour=polygon, area=area)

    if best_result is None:
        raise CardDetectionError(
            "Could not find a large 4-corner card outline. Reframe the card and try again."
        )

    return best_result


def _edge_lengths(points: np.ndarray) -> tuple[float, float]:
    rect = cv2.minAreaRect(points.reshape(-1, 1, 2))
    width, height = rect[1]
    return float(width), float(height)
