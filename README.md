# MTG Card Scanner

Phase 2 adds a minimal Tkinter desktop window with a live OpenCV webcam preview and image capture flow.

## Setup

Create or activate a virtual environment, then install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run the webcam app

Start the Tkinter scanner UI:

```powershell
python -m scanner_gui.app
```

The app will:

- Open the default webcam with `cv2.VideoCapture(0)`.
- Show a live preview in the window.
- Let you click `Capture` to freeze the current frame and save it to `data/scans/raw_<timestamp>.jpg`.
- Let you click `Retake` to resume the live preview.

If the webcam cannot be opened, the window shows a clear error message instead of the preview.

## Capture output

Captured images are written to `data/scans/`. The app creates `data/` and `data/scans/` automatically at runtime if they do not already exist.

## Local database commands

This project stores the SQLite database at `data/local.sqlite`.

Initialize the database:

```powershell
python -m db.init_db
```

Run the smoke test:

```powershell
python scripts/smoke_test_db.py
```
