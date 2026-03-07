# MTG Card Scanner

Phase 4 adds OCR over card regions of interest (ROIs) while keeping the Tkinter webcam preview and capture flow in the main GUI.

## Setup

Create or activate a virtual environment, then install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run the GUI

Start the scanner:

```powershell
python -m scanner_gui.app
```

The GUI keeps a live webcam preview inside the Tkinter window. Clicking `Capture` saves a fresh `raw_<timestamp>.jpg` image to `data/scans/`, then starts OCR in a background thread so the preview stays responsive.

## OCR behavior

- OCR uses relative ROIs sized from the saved image.
- `name_roi` reads the top band of the card.
- `collector_number_roi` reads the bottom-right band of the card.
- If a matching rectified image exists for the captured raw image, OCR uses the rectified image instead of the raw file.
- The GUI shows OCR text for both ROIs, per-ROI confidence, and overall confidence.

## Python 3.14 note

EasyOCR currently depends on PyTorch. On Python 3.14, a compatible `torch` build may not be available in your environment. When that happens, the app keeps the camera preview and capture working and shows:

```text
OCR unavailable on this Python version (torch not installed).
```

## Initialize the local database

This project stores the SQLite database at `data/local.sqlite`.

```powershell
python -m db.init_db
```

The init script creates the `data/` directory if it does not already exist and applies Alembic migrations to the latest revision.

## Run migrations manually

Upgrade to the latest migration:

```powershell
alembic upgrade head
```

Show the current revision:

```powershell
alembic current
```

Create a new migration after model changes:

```powershell
alembic revision --autogenerate -m "describe change"
```

## Smoke test

Run the database smoke test to initialize the database, insert a dummy card and inventory row, then print the stored quantity:

```powershell
python scripts/smoke_test_db.py
```
