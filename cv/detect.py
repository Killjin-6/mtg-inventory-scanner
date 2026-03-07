from __future__ import annotations

import math

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - depends on local environment
    cv2 = None
    np = None

TARGET_ASPECT_RATIO = 744 / 1039
MIN_AREA_RATIO = 0.02
MAX_CENTER_DISTANCE_RATIO = 0.45
DETECTION_MAX_DIMENSION = 1600


def _quad_aspect_ratio(quad_points) -> float:
    points = quad_points.reshape(4, 2).astype("float32")
    widths = [
        np.linalg.norm(points[0] - points[1]),
        np.linalg.norm(points[2] - points[3]),
    ]
    heights = [
        np.linalg.norm(points[1] - points[2]),
        np.linalg.norm(points[3] - points[0]),
    ]
    width = max(1.0, sum(widths) / 2.0)
    height = max(1.0, sum(heights) / 2.0)
    ratio = width / height
    if ratio > 1.0:
        return 1.0 / ratio
    return ratio


def _center_distance_ratio(quad_points, image_shape) -> float:
    image_height, image_width = image_shape[:2]
    image_center = np.array([image_width / 2.0, image_height / 2.0], dtype="float32")
    quad_center = quad_points.reshape(4, 2).mean(axis=0)
    distance = float(np.linalg.norm(quad_center - image_center))
    diagonal = math.hypot(image_width, image_height)
    return distance / max(1.0, diagonal)


def _resize_for_detection(image_bgr):
    image_height, image_width = image_bgr.shape[:2]
    longest_side = max(image_width, image_height)
    if longest_side <= DETECTION_MAX_DIMENSION:
        return image_bgr, 1.0

    scale = DETECTION_MAX_DIMENSION / float(longest_side)
    resized = cv2.resize(image_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return resized, scale


def _candidate_from_contour(contour):
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
    if len(approx) == 4:
        return approx.reshape(4, 2).astype("float32")

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    return box.astype("float32")


def _candidate_score(quad_points, contour_area, image_shape):
    aspect_ratio = _quad_aspect_ratio(quad_points)
    if not 0.60 <= aspect_ratio <= 0.85:
        return None

    center_distance = _center_distance_ratio(quad_points, image_shape)
    if center_distance > MAX_CENTER_DISTANCE_RATIO:
        return None

    return (
        contour_area,
        -abs(aspect_ratio - TARGET_ASPECT_RATIO),
        -center_distance,
    )


def detect_card_quad(image_bgr):
    if cv2 is None or np is None:
        return None
    if image_bgr is None or image_bgr.size == 0:
        return None

    working_image, scale = _resize_for_detection(image_bgr)
    image_height, image_width = working_image.shape[:2]
    image_area = float(image_width * image_height)

    gray = cv2.cvtColor(working_image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    thresholded = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    thresholded = cv2.morphologyEx(
        thresholded,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        iterations=2,
    )

    contour_sets = []
    contour_sets.append(cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
    contour_sets.append(cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])

    best_quad = None
    best_score = None

    for contours in contour_sets:
        for contour in contours:
            contour_area = cv2.contourArea(contour)
            if contour_area < image_area * MIN_AREA_RATIO:
                continue

            quad = _candidate_from_contour(contour)
            score = _candidate_score(quad, contour_area, working_image.shape)
            if score is None:
                continue

            if best_score is None or score > best_score:
                best_score = score
                best_quad = quad

    if best_quad is None:
        return None

    if scale != 1.0:
        return (best_quad / scale).astype("float32")
    return best_quad.astype("float32")
