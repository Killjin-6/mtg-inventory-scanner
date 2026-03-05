import tkinter as tk
from tkinter import ttk


def main() -> None:
    root = tk.Tk()
    root.title("MTG Scanner (MVP)")
    root.geometry("360x180")

    container = ttk.Frame(root, padding=16)
    container.pack(fill="both", expand=True)

    title = ttk.Label(container, text="Phase 0: Repo bootstrap", font=("Segoe UI", 12, "bold"))
    title.pack(anchor="w", pady=(0, 12))

    ttk.Label(container, text="Next: webcam preview, OCR, Scryfall, sync.").pack(anchor="w", pady=(0, 16))

    btn_row = ttk.Frame(container)
    btn_row.pack(anchor="w")

    capture_btn = ttk.Button(btn_row, text="Capture", state="disabled")
    capture_btn.pack(side="left", padx=(0, 8))

    confirm_btn = ttk.Button(btn_row, text="Confirm/Add", state="disabled")
    confirm_btn.pack(side="left")

    root.mainloop()


if __name__ == "__main__":
    main()