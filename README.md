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

Optional auth for hosted or shared use:

```powershell
$env:MTG_AUTH_USERNAME="scanner"
$env:MTG_AUTH_PASSWORD="choose-a-strong-password"
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
- serves inventory JSON at `GET /inventory`
- serves a small inventory browser at `GET /inventory/view`
- fixes EXIF orientation
- converts the image to RGB JPEG
- saves it as `raw_<timestamp>.jpg` in `data/scans/`
- attempts local card detection and perspective rectification
- saves `rectified_<timestamp>.jpg` next to the raw image when detection succeeds
- runs OCR on the rectified image when available, otherwise falls back to raw
- returns JSON with raw/rectified paths, detection status, OCR fields, and confidence values

The phone page also includes a `View Inventory` link that opens the HTML inventory browser.
It now also includes a slide-out `Recent Scans` drawer on the same page so you can review recent uploads without leaving `/phone`.

## Auth and Deployment Prep

Auth is optional by default. If `MTG_AUTH_USERNAME` and `MTG_AUTH_PASSWORD` are both set, the app protects the phone and inventory routes with HTTP Basic auth.

Current behavior:

- no auth env vars set: routes stay open for local/LAN use
- both auth env vars set: `/phone`, `/capture`, `/confirm-add`, `/scan-history`, `/inventory`, `/inventory/view`, and `/inventory/update` require Basic auth
- `GET /healthz` stays open for deployment health checks

Recommended deployment direction later:

- put the app behind a reverse proxy such as Nginx, Caddy, or a managed platform ingress
- terminate HTTPS at the proxy/platform
- keep strong auth credentials in environment variables, not in code
- move uploaded scan storage and secrets/config out of ad hoc local defaults before inviting outside users
- keep SQLite only for early hosted experiments; move to a server-grade database if concurrent multi-user use becomes real

## Inventory browser

The FastAPI inventory endpoints read from the same SQLite database used elsewhere in the project: `data/local.sqlite`.

JSON endpoint:

```text
GET /inventory
```

Supported query parameters:

- `q`: case-insensitive substring match on card name
- `color`: one of `W`, `U`, `B`, `R`, `G`
- `rarity`: one of `common`, `uncommon`, `rare`, `mythic`
- `set`: exact `set_code`
- `limit`: row limit, default `200`

Example:

```text
http://<YOUR_PC_LAN_IP>:8000/inventory?q=bolt&color=R&rarity=common&set=lea&limit=50
```

HTML endpoint:

```text
GET /inventory/view
```

Open it directly:

```text
http://<YOUR_PC_LAN_IP>:8000/inventory/view
```

The HTML page now follows the same visual direction as `/phone`, with a stronger header, cleaner filter card, and more polished table styling while keeping the same inline editing workflow.

From the HTML inventory browser, each row also includes:

- `+` to increment quantity
- `-` to decrement quantity
- `Remove` to delete the inventory row entirely
- inline editors for `reserved_quantity`, `foil`, and `condition`
- a `Save` action to update those metadata fields in place

The upload flow is now:

1. Save raw upload
2. Detect the card contour
3. Rectify the card perspective when detection succeeds
4. Run OCR on the rectified image
5. Fall back to OCR on the raw image if detection or rectification fails
6. Resolve the card against the local SQLite catalog
7. Confirm and add the resolved printing to local inventory

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
- `bottom_metadata_roi` reads the bottom-left metadata strip.
- The printed metadata strip is the primary print-identification zone and may include:
  - collector number
  - rarity
  - set code
  - language
- If a matching rectified image exists for the captured raw image, OCR uses the rectified image instead of the raw file.
- Matching now relies primarily on normalized `set_code + collector_number` against the local SQLite Scryfall catalog.
- If metadata parsing fails, the scanner still returns OCR text and an unresolved or fallback resolution result.
- After a card is resolved, the phone page can confirm the match and increment local inventory quantity while recording a `scan_event`.
- `scan_event` rows are now created for every upload attempt at `POST /capture`.
- Confirming an add updates that scan event to `confirmed` when the client includes the returned `scan_event_id`.
- Recent scan history is available from `GET /scan-history` and is used by the slide-out drawer in `/phone`.
- Exact matches can be confirmed directly.
- Fallback matches now require candidate review and selection before adding to inventory.
- Unresolved scans remain non-addable until resolution improves.

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
