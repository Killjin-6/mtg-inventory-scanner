from __future__ import annotations

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - depends on local environment
    cv2 = None
    np = None


def order_quad_points(quad_points):
    points = np.asarray(quad_points, dtype="float32")
    if points.shape != (4, 2):
        raise ValueError("quad_points must have shape (4, 2).")

    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)

    top_left = points[np.argmin(sums)]
    bottom_right = points[np.argmax(sums)]
    top_right = points[np.argmin(diffs)]
    bottom_left = points[np.argmax(diffs)]

    return np.array([top_left, top_right, bottom_right, bottom_left], dtype="float32")


def rectify_card(image_bgr, quad_points, output_size=(744, 1039)):
    if cv2 is None or np is None:
        raise RuntimeError("OpenCV is not available.")

    ordered = order_quad_points(quad_points)
    output_width, output_height = output_size
    destination = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype="float32",
    )

    transform = cv2.getPerspectiveTransform(ordered, destination)
    return cv2.warpPerspective(image_bgr, transform, (output_width, output_height))
