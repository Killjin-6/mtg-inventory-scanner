from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np

from cv.detect import CardDetectionError, detect_card
from cv.rectify import rectify_card, save_scan


WINDOW_TITLE = "MTG Scanner (Phase 3)"
PREVIEW_SIZE = (1280, 720)
CARD_RATIO = 63.0 / 88.0
TARGET_CAMERA_WIDTH = 1280
TARGET_CAMERA_HEIGHT = 720
TARGET_CAMERA_FPS = 60
BLUR_THRESHOLD = 120.0


class ScannerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("1360x900")
        self.root.minsize(1100, 760)
        self.capture: cv2.VideoCapture | None = None
        self.current_frame: np.ndarray | None = None
        self.preview_image: tk.PhotoImage | None = None
        self.preview_job: str | None = None
        self.blur_score: float = 0.0

        self.status_var = tk.StringVar(value="Opening camera...")
        self.camera_var = tk.StringVar(value="Camera: opening...")
        self.sharpness_var = tk.StringVar(value="Sharpness: waiting for frame")
        self.last_raw_var = tk.StringVar(value="Raw: waiting for capture")
        self.last_rectified_var = tk.StringVar(value="Rectified: waiting for capture")

        self._build_ui()
        self._open_camera()

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        title = ttk.Label(
            container,
            text="Phase 3: Single-card detect + rectify",
            font=("Segoe UI", 13, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 12))

        self.preview_label = ttk.Label(
            container,
            text="Starting camera...",
            anchor="center",
            relief="solid",
        )
        self.preview_label.grid(row=1, column=0, sticky="nsew")

        controls = ttk.Frame(container, padding=(0, 12, 0, 0))
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)

        ttk.Button(controls, text="Capture", command=self.capture_scan).grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=1, sticky="w")
        ttk.Label(controls, textvariable=self.camera_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Label(controls, textvariable=self.sharpness_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Label(controls, textvariable=self.last_raw_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Label(controls, textvariable=self.last_rectified_var).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

    def _open_camera(self) -> None:
        backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
        self.capture = cv2.VideoCapture(0, backend)
        if not self.capture.isOpened():
            self.status_var.set("Camera unavailable. Check that it is connected and free.")
            self.preview_label.configure(text="Camera unavailable.", image="")
            return

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_CAMERA_WIDTH)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_CAMERA_HEIGHT)
        self.capture.set(cv2.CAP_PROP_FPS, TARGET_CAMERA_FPS)

        actual_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.camera_var.set(f"Camera: {actual_width}x{actual_height} @ {actual_fps:.1f} FPS")
        self.status_var.set("Live preview ready. Fit one card inside the guide rectangle.")
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        self.preview_job = self.root.after(16, self._update_preview)

    def _update_preview(self) -> None:
        self.preview_job = None
        if self.capture is None or not self.capture.isOpened():
            return

        ok, frame = self.capture.read()
        if ok:
            self.current_frame = frame
            self.blur_score = self._blur_score(frame)
            preview = self._resize_for_preview(self._annotate_preview(frame))
            self.preview_image = self._frame_to_photoimage(preview)
            self.preview_label.configure(image=self.preview_image, text="")
            self.sharpness_var.set(self._sharpness_text(self.blur_score))
        else:
            self.status_var.set("Camera read failed. Close apps using the webcam and retry.")

        self._schedule_preview()

    def capture_scan(self) -> None:
        if self.current_frame is None:
            messagebox.showwarning("Capture failed", "No camera frame is available to capture yet.")
            return

        if self.blur_score < BLUR_THRESHOLD:
            messagebox.showwarning(
                "Frame too blurry",
                "Hold the card steady and wait for the sharpness indicator to read READY before capturing.",
            )
            return

        raw_path = save_scan(self.current_frame, "raw")
        self.last_raw_var.set(f"Raw: {raw_path}")

        try:
            guided_frame = self._crop_to_guide(self.current_frame)
            detection = detect_card(guided_frame)
            rectified = rectify_card(guided_frame, detection.corners)
            rectified_path = save_scan(rectified, "rectified")
        except CardDetectionError as exc:
            self.last_rectified_var.set("Rectified: detection failed")
            self.status_var.set(f"Detection failed: {exc}")
            messagebox.showwarning(
                "Card detection failed",
                f"{exc}\n\nKeep the card inside the guide rectangle.\n\nRaw image kept at:\n{raw_path}",
            )
            return
        except RuntimeError as exc:
            self.last_rectified_var.set("Rectified: save failed")
            self.status_var.set(str(exc))
            messagebox.showerror("Save failed", str(exc))
            return

        self.last_rectified_var.set(f"Rectified: {rectified_path}")
        self.status_var.set(f"Saved raw + rectified scans to {Path('data/scans')}.")

    def close(self) -> None:
        if self.preview_job is not None:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None

        if self.capture is not None:
            self.capture.release()
            self.capture = None

        self.root.destroy()

    @staticmethod
    def _resize_for_preview(frame: np.ndarray) -> np.ndarray:
        target_width, target_height = PREVIEW_SIZE
        height, width = frame.shape[:2]
        scale = min(target_width / width, target_height / height)
        resized_width = max(1, int(width * scale))
        resized_height = max(1, int(height * scale))
        return cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _guide_rect(frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        max_width = int(frame_width * 0.42)
        max_height = int(frame_height * 0.80)

        guide_height = min(max_height, int(max_width / CARD_RATIO))
        guide_width = int(guide_height * CARD_RATIO)

        if guide_width > max_width:
            guide_width = max_width
            guide_height = int(guide_width / CARD_RATIO)

        x1 = (frame_width - guide_width) // 2
        y1 = (frame_height - guide_height) // 2
        x2 = x1 + guide_width
        y2 = y1 + guide_height
        return x1, y1, x2, y2

    @classmethod
    def _annotate_preview(cls, frame: np.ndarray) -> np.ndarray:
        annotated = frame.copy()
        x1, y1, x2, y2 = cls._guide_rect(frame.shape[1], frame.shape[0])
        crop_x1, crop_y1, crop_x2, crop_y2 = cls._guide_crop_bounds(frame.shape[1], frame.shape[0])

        cv2.rectangle(annotated, (x1, y1), (x2, y2), (80, 220, 80), 3)
        cv2.putText(
            annotated,
            "Fit card inside guide",
            (x1, max(30, y1 - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (80, 220, 80),
            2,
            cv2.LINE_AA,
        )

        guided_frame = frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()
        try:
            detection = detect_card(guided_frame)
        except CardDetectionError:
            cv2.putText(
                annotated,
                "No card contour detected",
                (x1, min(frame.shape[0] - 16, y2 + 28)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (60, 140, 255),
                2,
                cv2.LINE_AA,
            )
            return annotated

        offset = np.array([crop_x1, crop_y1], dtype=np.float32)
        corners = detection.corners + offset
        corners = corners.astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(annotated, [corners], True, (40, 180, 255), 3, cv2.LINE_AA)
        cv2.putText(
            annotated,
            "Card contour locked",
            (x1, min(frame.shape[0] - 16, y2 + 28)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (40, 180, 255),
            2,
            cv2.LINE_AA,
        )
        return annotated

    @classmethod
    def _crop_to_guide(cls, frame: np.ndarray) -> np.ndarray:
        crop_x1, crop_y1, crop_x2, crop_y2 = cls._guide_crop_bounds(frame.shape[1], frame.shape[0])
        return frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()

    @classmethod
    def _guide_crop_bounds(cls, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = cls._guide_rect(frame_width, frame_height)
        pad_x = int((x2 - x1) * 0.08)
        pad_y = int((y2 - y1) * 0.08)

        crop_x1 = max(0, x1 - pad_x)
        crop_y1 = max(0, y1 - pad_y)
        crop_x2 = min(frame_width, x2 + pad_x)
        crop_y2 = min(frame_height, y2 + pad_y)
        return crop_x1, crop_y1, crop_x2, crop_y2

    @staticmethod
    def _blur_score(frame: np.ndarray) -> float:
        grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(grayscale, cv2.CV_64F).var())

    @staticmethod
    def _sharpness_text(score: float) -> str:
        status = "READY" if score >= BLUR_THRESHOLD else "too blurry"
        return f"Sharpness: {score:.0f} ({status}, threshold {BLUR_THRESHOLD:.0f})"

    @staticmethod
    def _frame_to_photoimage(frame: np.ndarray) -> tk.PhotoImage:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        header = f"P6 {width} {height} 255 ".encode("ascii")
        data = header + rgb.tobytes()
        return tk.PhotoImage(data=data, format="PPM")


def main() -> None:
    Path("data/scans").mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
