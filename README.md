# MTG Card Scanner

Phase 4 adds OCR over card regions of interest (ROIs) while keeping the Tkinter webcam preview and capture flow in the main GUI.

## Setup

Create or activate a virtual environment, then install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Phone capture upload

This branch adds a small FastAPI server so your phone can take a photo and upload it to the same `data/scans/` folder used by the desktop scanner.

Start the server on your PC:

```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Find your PC's LAN IP in PowerShell:

```powershell
ipconfig
```

Look for the `IPv4 Address` on your Wi-Fi adapter, then open this URL on your phone while both devices are on the same network:

```text
http://<YOUR_PC_LAN_IP>:8000/phone
```

The phone page uses a file input with camera capture support. After you take a photo, the server:

- accepts the upload at `POST /capture`
- fixes EXIF orientation
- converts the image to RGB JPEG
- saves it as `raw_<timestamp>.jpg` in `data/scans/`
- prefers a matching rectified image if one already exists
- runs OCR on the chosen image when EasyOCR is available
- returns JSON with the saved path, OCR fields, and confidence values

## Scryfall local catalog

This branch also adds a bulk importer so card printings can be resolved locally from SQLite instead of hitting Scryfall for every scan.

Initialize the database first:

```powershell
python -m db.init_db
```

Then import the Scryfall print catalog:

```powershell
python scripts/import_scryfall_bulk.py
```

What the importer does:

- fetches Scryfall bulk metadata from `https://api.scryfall.com/bulk-data`
- downloads the `default_cards` bulk file by default
- caches the downloaded JSON in `data/scryfall/`
- imports English printings into the existing `card_printing` table
- upserts by `scryfall_id` so reruns refresh existing rows

Useful options:

```powershell
python scripts/import_scryfall_bulk.py --source-file data\scryfall\default_cards.json
python scripts/import_scryfall_bulk.py --all-languages
python scripts/import_scryfall_bulk.py --bulk-type default_cards
```

`default_cards` is the recommended dataset here because it keeps print-level data suitable for set code + collector number matching without pulling every translated printing by default.

## Run the GUI

Start the scanner:

```powershell
python -m scanner_gui.app
```

The GUI keeps a live webcam preview inside the Tkinter window. Clicking `Capture` saves a fresh `raw_<timestamp>.jpg` image to `data/scans/`, then starts OCR in a background thread so the preview stays responsive.

To improve blurry captures, the app keeps a short rolling buffer of recent preview frames, computes a focus score, shows a live focus indicator, and saves the sharpest recent frame when you click `Capture`.

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
