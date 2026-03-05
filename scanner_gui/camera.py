from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import tkinter as tk


def frame_to_photoimage(frame) -> tk.PhotoImage:
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width, _ = rgb_frame.shape
    ppm_header = f"P6 {width} {height} 255 ".encode("ascii")
    ppm_data = ppm_header + rgb_frame.tobytes()
    return tk.PhotoImage(data=ppm_data, format="PPM")


class CameraController:
    def __init__(self, preview_size: tuple[int, int] = (960, 540)) -> None:
        self.preview_size = preview_size
        self.capture = cv2.VideoCapture(0)
        self.available = self.capture.isOpened()
        self.error_message: str | None = None
        self.frozen = False
        self.current_frame = None
        self.saved_frame = None
        self.output_dir = Path("data") / "scans"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.available:
            self.error_message = "Camera unavailable. Connect a webcam and restart the app."

    def read_frame(self):
        if not self.available or self.frozen:
            return self.saved_frame

        ok, frame = self.capture.read()
        if not ok:
            self.error_message = "Camera unavailable. Check that it is connected and not in use."
            self.available = False
            return None

        self.current_frame = frame
        return self._resize_for_preview(frame)

    def capture_frame(self) -> Path | None:
        if not self.available or self.current_frame is None:
            self.error_message = "No camera frame available to capture."
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"raw_{timestamp}.jpg"

        if not cv2.imwrite(str(output_path), self.current_frame):
            self.error_message = "Failed to save captured image."
            return None

        self.saved_frame = self._resize_for_preview(self.current_frame)
        self.frozen = True
        return output_path

    def get_display_frame(self):
        return self.saved_frame if self.frozen else self._resize_for_preview(self.current_frame)

    def resume_preview(self) -> None:
        self.frozen = False
        self.saved_frame = None

    def close(self) -> None:
        if self.capture is not None and self.capture.isOpened():
            self.capture.release()

    def _resize_for_preview(self, frame):
        width, height = self.preview_size
        return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
