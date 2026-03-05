from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from scanner_gui.camera import CameraController, frame_to_photoimage

WINDOW_TITLE = "MTG Scanner"
PREVIEW_SIZE = (960, 540)
PREVIEW_INTERVAL_MS = 40


class ScannerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("1000x700")
        self.root.minsize(760, 620)

        self.preview_job: str | None = None
        self.preview_image: tk.PhotoImage | None = None

        self.camera = CameraController(preview_size=PREVIEW_SIZE)

        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(
            container,
            text="Phase 2: Webcam capture",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self.preview_label = ttk.Label(
            container,
            text="Starting camera...",
            anchor="center",
            relief="solid",
        )
        self.preview_label.grid(row=1, column=0, sticky="nsew")

        self.status_var = tk.StringVar(value="Opening camera...")
        status_label = ttk.Label(container, textvariable=self.status_var)
        status_label.grid(row=2, column=0, sticky="w", pady=(12, 12))

        button_row = ttk.Frame(container)
        button_row.grid(row=3, column=0, sticky="w")

        self.capture_button = ttk.Button(button_row, text="Capture", command=self.capture_frame)
        self.capture_button.pack(side="left", padx=(0, 8))

        self.retake_button = ttk.Button(button_row, text="Retake", command=self.retake_frame, state="disabled")
        self.retake_button.pack(side="left")

        if self.camera.available:
            self.status_var.set("Live preview ready.")
            self.start_preview()
        else:
            self.capture_button.config(state="disabled")
            self.show_message(self.camera.error_message or "Camera unavailable.")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_preview(self) -> None:
        if not self.camera.available or self.camera.frozen:
            return

        frame = self.camera.read_frame()
        if frame is None:
            self.show_message("Camera is unavailable. Check that it is connected and not in use.")
            self.capture_button.config(state="disabled")
            return

        self.update_preview(frame)
        self.preview_job = self.root.after(PREVIEW_INTERVAL_MS, self.start_preview)

    def update_preview(self, frame) -> None:
        self.preview_image = frame_to_photoimage(frame)
        self.preview_label.config(image=self.preview_image, text="")

    def show_message(self, message: str) -> None:
        self.preview_label.config(image="", text=message)
        self.status_var.set(message)

    def capture_frame(self) -> None:
        saved_path = self.camera.capture_frame()
        if saved_path is None:
            self.show_message(self.camera.error_message or "Unable to capture frame.")
            return

        if self.preview_job is not None:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None

        frozen_frame = self.camera.get_display_frame()
        if frozen_frame is not None:
            self.update_preview(frozen_frame)

        self.capture_button.config(state="disabled")
        self.retake_button.config(state="normal")
        self.status_var.set(f"Saved image to {saved_path.as_posix()}")

    def retake_frame(self) -> None:
        if not self.camera.available:
            return

        self.camera.resume_preview()
        self.capture_button.config(state="normal")
        self.retake_button.config(state="disabled")
        self.status_var.set("Live preview resumed.")
        self.start_preview()

    def on_close(self) -> None:
        if self.preview_job is not None:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None

        self.camera.close()
        self.root.destroy()


def main() -> None:
    Path("data/scans").mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
