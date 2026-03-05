# MTG Card Scanner

Phase 3 adds a minimal desktop capture flow that detects a single Magic card in the webcam frame and rectifies it into a flat scan.

## Setup

Create or activate a virtual environment, then install dependencies:

```powershell
python -m pip install -r requirements.txt
```

This phase expects OpenCV and NumPy to be available in the environment because the scanner GUI uses webcam capture and perspective warping.

## Run the scanner GUI

Start the desktop app:

```powershell
python -m scanner_gui.app
```

Usage:

1. Position one card so it dominates the webcam frame.
2. Fit it inside the green guide rectangle and wait until the sharpness indicator reports `READY`.
3. The preview attempts live contour detection and outlines the detected card in orange when it locks on.
4. Click `Capture`.
5. The app always saves the raw image to `data/scans/raw_<timestamp>.jpg`.
6. If a large 4-corner card contour is found, it also saves a warped scan to `data/scans/rectified_<timestamp>.jpg`.
7. If detection fails, the GUI shows a warning and keeps the raw capture on disk.

The app requests a 1920x1080 webcam feed at 30 FPS and displays the actual camera mode negotiated by OpenCV. Some webcams may fall back to a lower supported mode.

## Rectification pipeline

The single-card MVP uses a contour-based pipeline:

1. Convert the frame to grayscale.
2. Apply Gaussian blur.
3. Run Canny edge detection.
4. Find contours.
5. Select the largest reasonable quadrilateral.
6. Apply a perspective transform to warp the card into a flat rectangle.

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
