from __future__ import annotations

from collections import deque
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

try:
    import cv2
except Exception:  # pragma: no cover - depends on local environment
    cv2 = None

from PIL import Image, ImageTk

from ocr.easyocr_reader import OCRResults, get_easyocr_reader, ocr_availability_message

ROOT_DIR = Path(__file__).resolve().parents[1]
SCANS_DIR = ROOT_DIR / "data" / "scans"
PREVIEW_SIZE = (640, 480)
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
FRAME_BUFFER_SIZE = 8
FOCUS_POOR_THRESHOLD = 80.0
FOCUS_FAIR_THRESHOLD = 160.0


def preferred_ocr_image(raw_path: Path) -> Path:
    token = raw_path.stem.removeprefix("raw_")
    candidates = [
        raw_path.with_name(raw_path.name.replace("raw_", "rectified_", 1)),
        raw_path.with_name(f"{raw_path.stem}_rectified{raw_path.suffix}"),
        raw_path.with_name(f"rectified_{token}{raw_path.suffix}"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    for sibling in raw_path.parent.iterdir():
        if not sibling.is_file() or sibling.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        stem_lower = sibling.stem.lower()
        if "rectified" in stem_lower and token.lower() in stem_lower:
            return sibling

    return raw_path


def overall_confidence(results: OCRResults) -> float:
    if not results:
        return 0.0
    return sum(confidence for _, confidence in results.values()) / len(results)


def focus_score(frame) -> float:
    grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(grayscale, cv2.CV_64F).var())


def focus_label(score: float) -> str:
    if score < FOCUS_POOR_THRESHOLD:
        return "Poor"
    if score < FOCUS_FAIR_THRESHOLD:
        return "Fair"
    return "Good"


class ScannerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MTG Scanner")
        self.root.geometry("980x760")

        self.camera = None
        self.current_frame = None
        self.frame_buffer: deque[tuple[float, object]] = deque(maxlen=FRAME_BUFFER_SIZE)
        self.preview_image = None
        self.preview_running = False
        self.ocr_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.ocr_in_progress = False

        self.status_var = tk.StringVar(value="Starting camera...")
        self.image_var = tk.StringVar(value="Image: none")
        self.name_text_var = tk.StringVar(value="")
        self.name_conf_var = tk.StringVar(value="Name confidence: 0.00")
        self.collector_text_var = tk.StringVar(value="")
        self.collector_conf_var = tk.StringVar(value="Collector confidence: 0.00")
        self.overall_conf_var = tk.StringVar(value="Overall confidence: 0.00")
        self.ocr_runtime_var = tk.StringVar(value=self._ocr_runtime_text())
        self.focus_var = tk.StringVar(value="Focus: waiting for camera")

        container = ttk.Frame(root, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Phase 4: Tkinter preview + OCR", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", pady=(0, 12)
        )

        content = ttk.Frame(container)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)

        preview_frame = ttk.LabelFrame(content, text="Webcam Preview", padding=12)
        preview_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.preview_label = ttk.Label(preview_frame, text="Camera unavailable.", anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        controls = ttk.Frame(preview_frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        self.capture_button = ttk.Button(controls, text="Capture", command=self.capture)
        self.capture_button.pack(side="left")
        ttk.Label(controls, textvariable=self.focus_var).pack(side="left", padx=(12, 0))

        details_frame = ttk.LabelFrame(content, text="Scan Results", padding=12)
        details_frame.grid(row=0, column=1, sticky="nsew")
        details_frame.columnconfigure(1, weight=1)

        ttk.Label(details_frame, textvariable=self.status_var, wraplength=280).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        ttk.Label(details_frame, textvariable=self.ocr_runtime_var, wraplength=280).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        ttk.Label(details_frame, textvariable=self.focus_var, wraplength=280).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        ttk.Label(details_frame, textvariable=self.image_var, wraplength=280).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, 14)
        )

        ttk.Label(details_frame, text="Name").grid(row=4, column=0, sticky="nw", padx=(0, 8))
        ttk.Label(details_frame, textvariable=self.name_text_var, wraplength=220).grid(row=4, column=1, sticky="w")
        ttk.Label(details_frame, textvariable=self.name_conf_var).grid(row=5, column=1, sticky="w", pady=(2, 10))

        ttk.Label(details_frame, text="Collector #").grid(row=6, column=0, sticky="nw", padx=(0, 8))
        ttk.Label(details_frame, textvariable=self.collector_text_var, wraplength=220).grid(
            row=6, column=1, sticky="w"
        )
        ttk.Label(details_frame, textvariable=self.collector_conf_var).grid(
            row=7, column=1, sticky="w", pady=(2, 10)
        )

        ttk.Label(details_frame, textvariable=self.overall_conf_var).grid(row=8, column=0, columnspan=2, sticky="w")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._start_camera()
        self._poll_ocr_queue()

    def _ocr_runtime_text(self) -> str:
        message = ocr_availability_message()
        if message is None:
            return "OCR ready."
        return message

    def _start_camera(self) -> None:
        if cv2 is None:
            self.status_var.set("Camera unavailable: OpenCV is not installed.")
            self.capture_button.state(["disabled"])
            return

        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened():
            self.status_var.set("Camera unavailable: unable to open device 0.")
            self.capture_button.state(["disabled"])
            return

        self.preview_running = True
        self.status_var.set("Live preview ready.")
        self.capture_button.state(["!disabled"])
        self._update_preview()

    def _update_preview(self) -> None:
        if not self.preview_running or self.camera is None:
            return

        ok, frame = self.camera.read()
        if ok and frame is not None:
            self.current_frame = frame
            score = focus_score(frame)
            self.frame_buffer.append((score, frame.copy()))
            self.focus_var.set(f"Focus: {focus_label(score)} ({score:.0f})")
            self._render_frame(frame)
        else:
            self.status_var.set("Camera preview stalled.")

        self.root.after(30, self._update_preview)

    def _render_frame(self, frame) -> None:
        preview = frame.copy()
        height, width = preview.shape[:2]
        guide_margin_x = int(width * 0.12)
        guide_margin_y = int(height * 0.10)
        cv2.rectangle(
            preview,
            (guide_margin_x, guide_margin_y),
            (width - guide_margin_x, height - guide_margin_y),
            (0, 220, 0),
            2,
        )
        rgb_frame = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb_frame)
        image.thumbnail(PREVIEW_SIZE)
        self.preview_image = ImageTk.PhotoImage(image=image)
        self.preview_label.configure(image=self.preview_image, text="")

    def capture(self) -> None:
        if not self.frame_buffer:
            self.status_var.set("No camera frame available to capture.")
            return

        SCANS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_path = SCANS_DIR / f"raw_{timestamp}.jpg"
        sharpest_score, sharpest_frame = max(self.frame_buffer, key=lambda item: item[0])

        if not cv2.imwrite(str(raw_path), sharpest_frame):
            self.status_var.set("Failed to save captured image.")
            return

        self.image_var.set(f"Image: {raw_path}")
        self.status_var.set(
            f"Capture saved using sharpest recent frame ({focus_label(sharpest_score)}, {sharpest_score:.0f}). "
            "Running OCR in background..."
        )
        self._start_ocr(raw_path)

    def _start_ocr(self, raw_path: Path) -> None:
        if self.ocr_in_progress:
            self.status_var.set("OCR already running for the last capture.")
            return

        self.ocr_in_progress = True
        self.capture_button.state(["disabled"])
        self._set_ocr_results({})

        worker = threading.Thread(target=self._ocr_worker, args=(raw_path,), daemon=True)
        worker.start()

    def _ocr_worker(self, raw_path: Path) -> None:
        target_path = preferred_ocr_image(raw_path)
        availability_error = ocr_availability_message()
        if availability_error is not None:
            self.ocr_queue.put(("unavailable", {"message": availability_error, "image_path": target_path}))
            return

        try:
            reader = get_easyocr_reader()
            results = reader.read_rois(target_path)
        except Exception as exc:
            self.ocr_queue.put(("failed", {"message": f"OCR failed: {exc}", "image_path": target_path}))
            return

        self.ocr_queue.put(("success", {"results": results, "image_path": target_path}))

    def _poll_ocr_queue(self) -> None:
        try:
            while True:
                event, payload = self.ocr_queue.get_nowait()
                self._handle_ocr_event(event, payload)
        except queue.Empty:
            pass

        self.root.after(100, self._poll_ocr_queue)

    def _handle_ocr_event(self, event: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        self.ocr_in_progress = False
        if self.camera is not None and self.camera.isOpened():
            self.capture_button.state(["!disabled"])

        image_path = data.get("image_path")
        self.image_var.set(f"Image: {image_path}" if image_path is not None else "Image: none")

        if event == "success":
            results = data.get("results", {})
            if isinstance(results, dict):
                self._set_ocr_results(results)
            else:
                self._set_ocr_results({})
            self.status_var.set("OCR complete.")
            return

        self._set_ocr_results({})
        self.status_var.set(str(data.get("message", "OCR failed.")))

    def _set_ocr_results(self, results: OCRResults) -> None:
        name_text, name_conf = results.get("name_roi", ("", 0.0))
        collector_text, collector_conf = results.get("collector_number_roi", ("", 0.0))

        self.name_text_var.set(name_text)
        self.name_conf_var.set(f"Name confidence: {name_conf:.2f}")
        self.collector_text_var.set(collector_text)
        self.collector_conf_var.set(f"Collector confidence: {collector_conf:.2f}")
        self.overall_conf_var.set(f"Overall confidence: {overall_confidence(results):.2f}")

    def on_close(self) -> None:
        self.preview_running = False
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
