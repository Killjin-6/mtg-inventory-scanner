from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image, ImageOps
from pydantic import BaseModel
from sqlalchemy import select

try:
    import cv2
except Exception:  # pragma: no cover - depends on local environment
    cv2 = None

from cv.detect import detect_card_quad
from cv.rectify import rectify_card
from db.card_resolution import resolve_card_printing
from db.models import CardPrinting, InventoryItem, ScanEvent
from db.repo import SessionLocal
from ocr.easyocr_reader import OCRResults, extract_parsed_metadata, get_easyocr_reader, ocr_availability_message

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[1]
SCANS_DIR = ROOT_DIR / "data" / "scans"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
JPEG_QUALITY = 92
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

APP_SHELL_CSS = """
:root {
  color-scheme: light;
  --bg: #f4efe6;
  --bg-accent: #efe4d5;
  --surface: rgba(255, 251, 246, 0.82);
  --surface-strong: #fffaf4;
  --surface-muted: rgba(255, 255, 255, 0.68);
  --ink: #1f1a15;
  --muted: #6f655a;
  --line: rgba(101, 83, 59, 0.18);
  --line-strong: rgba(101, 83, 59, 0.28);
  --primary: #1f6a52;
  --primary-strong: #154c3b;
  --primary-soft: rgba(31, 106, 82, 0.11);
  --secondary: #f1e4d2;
  --secondary-ink: #4f4235;
  --danger: #a14c40;
  --danger-strong: #7f372e;
  --shadow: 0 24px 56px rgba(33, 25, 17, 0.12);
  --shadow-soft: 0 14px 30px rgba(33, 25, 17, 0.06);
  --chip-exact-bg: rgba(27, 122, 76, 0.12);
  --chip-exact-text: #176743;
  --chip-fallback-bg: rgba(176, 124, 25, 0.14);
  --chip-fallback-text: #8a5d08;
  --chip-unresolved-bg: rgba(96, 91, 84, 0.14);
  --chip-unresolved-text: #5c5750;
}

* {
  box-sizing: border-box;
}

html {
  background: linear-gradient(180deg, #f8f4ee, var(--bg));
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: "Segoe UI", sans-serif;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(31, 106, 82, 0.16), transparent 32%),
    radial-gradient(circle at bottom right, rgba(161, 76, 64, 0.08), transparent 24%),
    linear-gradient(180deg, #faf7f2, var(--bg));
}

a {
  color: inherit;
}

button,
input,
select {
  font: inherit;
}

.app-shell {
  width: min(100%, 1100px);
  margin: 0 auto;
  padding: 16px;
}

.app-stack {
  display: grid;
  gap: 16px;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  padding-top: 10px;
}

.app-header-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: rgba(255, 250, 244, 0.84);
  backdrop-filter: blur(18px);
  box-shadow: var(--shadow-soft);
}

.app-brand {
  display: grid;
  gap: 4px;
}

.app-kicker {
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--primary);
}

.app-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.app-subtitle {
  margin: 0;
  color: var(--muted);
  line-height: 1.5;
  font-size: 0.95rem;
}

.app-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.app-nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--secondary-ink);
  text-decoration: none;
  font-weight: 700;
  box-shadow: var(--shadow-soft);
}

.app-nav-link.is-active {
  background: linear-gradient(135deg, var(--primary), var(--primary-strong));
  color: #fff;
  border-color: transparent;
}

.page-hero,
.app-card {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: var(--surface);
  backdrop-filter: blur(20px);
  box-shadow: var(--shadow);
}

.page-hero::before,
.app-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 120px;
  background:
    radial-gradient(circle at top left, rgba(31, 106, 82, 0.14), transparent 48%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.36), transparent);
  pointer-events: none;
}

.page-hero-inner,
.app-card-inner {
  position: relative;
  padding: 20px;
}

.page-hero-inner {
  display: grid;
  gap: 18px;
}

.eyebrow {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid var(--line);
  color: var(--primary);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-title {
  margin: 0;
  font-size: clamp(2rem, 6vw, 3rem);
  line-height: 0.98;
  letter-spacing: -0.04em;
}

.page-copy {
  margin: 0;
  max-width: 56ch;
  color: var(--muted);
  line-height: 1.6;
}

.hero-metrics {
  display: grid;
  gap: 12px;
}

.metric-card {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.7);
}

.metric-label {
  margin: 0 0 6px;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.metric-value {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.45;
}

.section-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.section-title {
  margin: 0;
  font-size: 1.12rem;
  letter-spacing: -0.02em;
}

.section-copy {
  margin: 0;
  color: var(--muted);
  line-height: 1.55;
  font-size: 0.95rem;
}

.toolbar-grid,
.form-grid {
  display: grid;
  gap: 12px;
}

.field {
  display: grid;
  gap: 6px;
}

.field-label {
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.control,
.button {
  width: 100%;
  min-height: 46px;
  border-radius: 16px;
}

.control {
  padding: 12px 14px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 12px 16px;
  border: 0;
  cursor: pointer;
  font-weight: 800;
  text-decoration: none;
  box-shadow: 0 14px 28px rgba(21, 76, 59, 0.18);
}

.button:disabled {
  cursor: default;
  opacity: 0.6;
  box-shadow: none;
}

.button.primary {
  background: linear-gradient(135deg, var(--primary), var(--primary-strong));
  color: #fff;
}

.button.secondary {
  background: linear-gradient(180deg, #f2e8dc, #e7d7c4);
  color: var(--secondary-ink);
  box-shadow: none;
  border: 1px solid rgba(101, 83, 59, 0.14);
}

.button.danger {
  background: linear-gradient(135deg, var(--danger), var(--danger-strong));
  color: #fff;
  box-shadow: none;
}

.button.small {
  width: auto;
  min-height: 40px;
  padding: 10px 12px;
  border-radius: 14px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.82);
  color: var(--secondary-ink);
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: capitalize;
}

.chip.exact {
  background: var(--chip-exact-bg);
  color: var(--chip-exact-text);
  border-color: rgba(23, 103, 67, 0.16);
}

.chip.fallback {
  background: var(--chip-fallback-bg);
  color: var(--chip-fallback-text);
  border-color: rgba(138, 93, 8, 0.16);
}

.chip.unresolved {
  background: var(--chip-unresolved-bg);
  color: var(--chip-unresolved-text);
  border-color: rgba(92, 87, 80, 0.16);
}

.chip.confirmed {
  background: var(--chip-exact-bg);
  color: var(--chip-exact-text);
}

@media (min-width: 760px) {
  .app-shell {
    padding: 20px;
  }

  .app-header-inner {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }

  .page-hero-inner {
    grid-template-columns: minmax(0, 1.35fr) minmax(240px, 0.65fr);
    align-items: start;
  }
}
""".strip()

PHONE_PAGE_CSS = """
.upload-grid,
.results-grid,
.details-grid {
  display: grid;
  gap: 12px;
}

.results-grid,
.details-grid {
  grid-template-columns: 1fr;
}

.result-card {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow: var(--shadow-soft);
}

.result-card.featured {
  background: linear-gradient(180deg, rgba(31, 106, 82, 0.12), rgba(255, 255, 255, 0.88));
}

.result-label {
  margin: 0 0 6px;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.result-value {
  margin: 0;
  word-break: break-word;
  line-height: 1.5;
}

.result-value.emphasis {
  font-size: 1.12rem;
  font-weight: 800;
}

.status-banner {
  min-height: 24px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.75);
  white-space: pre-wrap;
  box-shadow: var(--shadow-soft);
}

.status-banner[data-tone="success"] {
  background: rgba(27, 122, 76, 0.09);
  border-color: rgba(23, 103, 67, 0.18);
}

.status-banner[data-tone="warn"] {
  background: rgba(176, 124, 25, 0.1);
  border-color: rgba(138, 93, 8, 0.18);
}

.status-banner[data-tone="danger"] {
  background: rgba(161, 76, 64, 0.1);
  border-color: rgba(127, 55, 46, 0.18);
}

.help-note {
  padding: 14px 16px;
  border: 1px dashed var(--line-strong);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
  color: var(--muted);
  line-height: 1.55;
}

.file-name {
  color: var(--muted);
  font-size: 0.94rem;
}

.candidate-list {
  display: grid;
  gap: 10px;
}

.candidate-option {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
}

.candidate-option input {
  margin-top: 3px;
}

.history-toggle {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 12;
}

.history-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(23, 18, 13, 0.36);
  opacity: 0;
  pointer-events: none;
  transition: opacity 180ms ease;
  z-index: 11;
}

.history-backdrop.open {
  opacity: 1;
  pointer-events: auto;
}

.history-drawer {
  position: fixed;
  right: 12px;
  bottom: 12px;
  top: 12px;
  width: min(100vw - 24px, 390px);
  z-index: 13;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: rgba(255, 250, 244, 0.95);
  backdrop-filter: blur(22px);
  box-shadow: var(--shadow);
  overflow-y: auto;
  transform: translateX(calc(100% + 24px));
  transition: transform 220ms ease;
}

.history-drawer.open {
  transform: translateX(0);
}

.history-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.history-list {
  display: grid;
  gap: 10px;
}

.history-item,
.history-empty {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
}

.history-item.active {
  background: linear-gradient(180deg, rgba(31, 106, 82, 0.11), rgba(255, 255, 255, 0.88));
  border-color: rgba(31, 106, 82, 0.22);
}

.history-item-title {
  font-weight: 800;
  margin-bottom: 4px;
}

.history-item-meta,
.history-empty {
  color: var(--muted);
  line-height: 1.45;
  font-size: 0.92rem;
}

@media (min-width: 760px) {
  .upload-grid {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
  }

  .results-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .details-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
""".strip()


def render_app_nav(active_path: str) -> str:
    links = [
        ("/phone", "Phone Scan"),
        ("/inventory/view", "Inventory"),
        ("/scan-history", "Scan History"),
    ]
    rendered = []
    for href, label in links:
        classes = "app-nav-link"
        if href == active_path:
            classes += " is-active"
        rendered.append(f'<a class="{classes}" href="{href}">{escape(label)}</a>')
    return "\n".join(rendered)


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


class ConfirmAddRequest(BaseModel):
    scan_event_id: int | None = None
    scryfall_id: str
    image_path: str | None = None
    ocr_name: str | None = None
    ocr_set_code: str | None = None
    ocr_collector_number: str | None = None
    confidence: float | None = None


def capture_scan_status(resolution: dict[str, object]) -> str:
    status = str(resolution.get("status") or "unresolved")
    if status == "exact_match":
        return "captured_exact_match"
    if status == "fallback_match":
        return "captured_needs_review"
    return "captured_unresolved"


def serialize_scan_event(event: ScanEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "captured_at": event.captured_at.isoformat() if event.captured_at else None,
        "image_path": event.image_path,
        "ocr_name": event.ocr_name,
        "ocr_set_code": event.ocr_set_code,
        "ocr_collector_number": event.ocr_collector_number,
        "confidence": event.confidence,
        "resolved_scryfall_id": event.resolved_scryfall_id,
        "status": event.status,
    }


@router.get("/scan-history")
async def scan_history(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, object]]:
    with SessionLocal() as session:
        events = session.execute(select(ScanEvent).order_by(ScanEvent.id.desc()).limit(limit)).scalars().all()
    return [serialize_scan_event(event) for event in events]


@router.get("/phone", response_class=HTMLResponse)
async def phone_page() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MTG Phone Capture</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #efe8dc;
      --panel: rgba(255, 250, 243, 0.86);
      --panel-strong: #fffaf3;
      --ink: #1f1b16;
      --muted: #6d645a;
      --accent: #1d7a57;
      --accent-strong: #0f5e40;
      --accent-soft: rgba(29, 122, 87, 0.12);
      --border: rgba(125, 108, 86, 0.22);
      --danger: #a34840;
      --warn: #9a6d27;
      --success: #17744d;
      --shadow: 0 28px 64px rgba(41, 31, 22, 0.14);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(29, 122, 87, 0.22), transparent 32%),
        radial-gradient(circle at bottom right, rgba(163, 72, 64, 0.11), transparent 30%),
        linear-gradient(180deg, #f8f4ee, var(--bg));
      color: var(--ink);
      padding: 28px 18px;
    }
    .shell {
      position: relative;
      width: min(100%, 1180px);
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(0, 820px);
      justify-content: center;
    }
    .panel {
      position: relative;
      background: var(--panel);
      backdrop-filter: blur(18px);
      border: 1px solid var(--border);
      border-radius: 30px;
      padding: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .panel::before {
      content: "";
      position: absolute;
      inset: 0 0 auto 0;
      height: 150px;
      background:
        radial-gradient(circle at top left, rgba(29, 122, 87, 0.16), transparent 45%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.45), transparent);
      pointer-events: none;
    }
    .hero {
      position: relative;
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(230px, 0.7fr);
      gap: 18px;
      margin-bottom: 18px;
    }
    .hero-copy {
      display: grid;
      gap: 12px;
    }
    .eyebrow {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid var(--border);
      color: var(--accent-strong);
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    h1 {
      margin: 0;
      font-size: clamp(1.85rem, 3vw, 2.7rem);
      line-height: 1.03;
      letter-spacing: -0.03em;
      max-width: 12ch;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
      max-width: 56ch;
      font-size: 1rem;
    }
    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .action-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 12px 15px;
      border-radius: 999px;
      border: 1px solid var(--border);
      text-decoration: none;
      color: var(--ink);
      background: rgba(255, 255, 255, 0.74);
      font-weight: 700;
      box-shadow: 0 10px 22px rgba(31, 27, 22, 0.06);
    }
    .action-link.primary {
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: white;
      border-color: transparent;
    }
    .summary-card,
    .guide,
    .upload-card,
    .result-section,
    .history-item {
      border: 1px solid var(--border);
      box-shadow: 0 10px 24px rgba(31, 27, 22, 0.05);
    }
    .summary-card {
      background: rgba(255, 255, 255, 0.64);
      border-radius: 22px;
      padding: 18px;
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .summary-stat {
      display: grid;
      gap: 4px;
    }
    .summary-label {
      font-size: 0.76rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }
    .summary-value {
      font-size: 1.05rem;
      font-weight: 700;
      line-height: 1.35;
    }
    .guide {
      margin: 0 0 18px;
      padding: 15px 16px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.58);
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.55;
      border-style: dashed;
    }
    .upload-card {
      display: grid;
      gap: 14px;
      margin-bottom: 16px;
      background: rgba(255, 255, 255, 0.66);
      border-radius: 22px;
      padding: 18px;
    }
    .upload-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }
    .upload-title {
      margin: 0;
      font-size: 1rem;
    }
    .upload-copy {
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 0.94rem;
    }
    .history-tab {
      position: fixed;
      top: 30px;
      right: 22px;
      writing-mode: vertical-rl;
      text-orientation: mixed;
      border-radius: 20px;
      padding: 16px 12px;
      background: linear-gradient(180deg, #22382d, #14231c);
      color: white;
      border: 0;
      box-shadow: 0 18px 36px rgba(31, 27, 22, 0.18);
      z-index: 5;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      width: auto;
    }
    .history-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(25, 19, 14, 0.38);
      opacity: 0;
      pointer-events: none;
      transition: opacity 180ms ease;
      z-index: 4;
    }
    .history-backdrop.open {
      opacity: 1;
      pointer-events: auto;
    }
    .history-drawer {
      position: fixed;
      top: 18px;
      right: 18px;
      bottom: 18px;
      width: min(100vw - 24px, 390px);
      background: rgba(255, 249, 241, 0.97);
      backdrop-filter: blur(18px);
      border-radius: 28px;
      padding: 20px;
      transform: translateX(calc(100% + 16px));
      transition: transform 220ms ease;
      z-index: 6;
      overflow-y: auto;
    }
    .history-drawer.open {
      transform: translateX(0);
    }
    .history-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .history-title {
      margin: 0;
      font-size: 1.12rem;
    }
    .history-subtitle {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.45;
    }
    .history-list {
      display: grid;
      gap: 12px;
    }
    .history-item {
      padding: 14px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.82);
    }
    .history-item.active {
      background: linear-gradient(180deg, rgba(29, 122, 87, 0.1), rgba(255, 255, 255, 0.86));
      border-color: rgba(29, 122, 87, 0.28);
    }
    .history-item-title {
      font-weight: 700;
      margin-bottom: 4px;
    }
    .history-item-meta {
      color: var(--muted);
      font-size: 0.86rem;
      line-height: 1.4;
    }
    .history-badge {
      display: inline-block;
      margin-top: 8px;
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(28, 124, 84, 0.12);
      color: var(--accent-strong);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .history-badge.confirmed {
      background: rgba(23, 116, 77, 0.12);
      color: var(--success);
    }
    .history-badge.captured_needs_review {
      background: rgba(154, 109, 39, 0.12);
      color: var(--warn);
    }
    .history-badge.captured_unresolved {
      background: rgba(163, 72, 64, 0.12);
      color: var(--danger);
    }
    .history-empty {
      color: var(--muted);
      font-size: 0.92rem;
      padding: 10px 2px;
    }
    .native-input,
    button {
      width: 100%;
      border-radius: 14px;
      padding: 14px 16px;
      font-size: 1rem;
      font: inherit;
    }
    .native-input {
      border: 1px solid var(--border);
      background: white;
    }
    button {
      border: 0;
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: white;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 12px 24px rgba(15, 94, 64, 0.18);
    }
    button:disabled {
      background: #8fb5a3;
      cursor: default;
      box-shadow: none;
    }
    .secondary-button {
      background: linear-gradient(135deg, #2c4135, #1d2d24);
    }
    .small-button {
      width: auto;
      padding: 10px 12px;
      border-radius: 12px;
      box-shadow: none;
    }
    .file-name {
      color: var(--muted);
      font-size: 0.94rem;
    }
    .status {
      min-height: 24px;
      font-size: 0.95rem;
      color: var(--ink);
      white-space: pre-wrap;
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.72);
      margin-bottom: 18px;
    }
    .status[data-tone="success"] {
      background: rgba(23, 116, 77, 0.1);
      border-color: rgba(23, 116, 77, 0.22);
    }
    .status[data-tone="warn"] {
      background: rgba(154, 109, 39, 0.12);
      border-color: rgba(154, 109, 39, 0.22);
    }
    .status[data-tone="danger"] {
      background: rgba(163, 72, 64, 0.11);
      border-color: rgba(163, 72, 64, 0.22);
    }
    .results {
      display: grid;
      gap: 18px;
    }
    .result-section {
      background: rgba(255, 255, 255, 0.64);
      border-radius: 22px;
      padding: 18px;
    }
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 12px;
      margin-bottom: 12px;
    }
    .section-title {
      margin: 0;
      font-size: 1rem;
    }
    .section-copy {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.45;
    }
    .result-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .result-label {
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .result-value {
      font-size: 1rem;
      color: var(--ink);
      word-break: break-word;
      line-height: 1.45;
    }
    .result-card {
      padding: 14px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.76);
      border: 1px solid rgba(125, 108, 86, 0.14);
    }
    .result-card.hero-card {
      background: linear-gradient(135deg, rgba(29, 122, 87, 0.1), rgba(255, 255, 255, 0.84));
      border-color: rgba(29, 122, 87, 0.2);
    }
    .result-value.emphasis {
      font-size: 1.15rem;
      font-weight: 700;
    }
    .badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.82);
      color: var(--muted);
      font-size: 0.82rem;
      font-weight: 700;
    }
    .badge.good {
      color: var(--success);
      background: rgba(23, 116, 77, 0.1);
    }
    .badge.warn {
      color: var(--warn);
      background: rgba(154, 109, 39, 0.1);
    }
    .badge.danger {
      color: var(--danger);
      background: rgba(163, 72, 64, 0.1);
    }
    .candidate-list {
      margin-top: 14px;
      border-top: 1px solid var(--border);
      padding-top: 14px;
    }
    .candidate-option {
      display: block;
      margin-bottom: 10px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.7);
    }
    .candidate-option input {
      margin-right: 10px;
    }
    @media (max-width: 940px) {
      .hero {
        grid-template-columns: 1fr;
      }
      .history-tab {
        top: 18px;
        right: 18px;
      }
      .history-drawer {
        width: min(100vw - 20px, 390px);
      }
    }
    @media (max-width: 640px) {
      body {
        padding: 14px;
      }
      .panel {
        padding: 22px 18px;
        border-radius: 26px;
      }
      .result-grid {
        grid-template-columns: 1fr;
      }
      .history-tab {
        writing-mode: horizontal-tb;
        text-orientation: initial;
        padding: 10px 14px;
        border-radius: 999px;
        top: 12px;
        right: 12px;
      }
      .history-drawer {
        top: 10px;
        right: 10px;
        bottom: 10px;
        width: calc(100vw - 20px);
      }
    }
  </style>
</head>
<body>
  <div id="history-backdrop" class="history-backdrop" hidden></div>
  <div class="shell">
    <main class="panel">
      <section class="hero">
        <div class="hero-copy">
          <div class="eyebrow">Local Capture Workflow</div>
          <h1>Scan a card, review the match, and confirm it quickly.</h1>
          <p class="subtitle">This page is the intake surface for your scanner. Keep the capture loop tight on mobile, keep recent scans in the drawer, and only leave the page when you want broader inventory management.</p>
          <div class="hero-actions">
            <a class="action-link primary" href="/inventory/view">View Inventory</a>
            <a class="action-link" href="/inventory">Inventory JSON</a>
          </div>
        </div>
        <aside class="summary-card">
          <div class="summary-stat">
            <div class="summary-label">Workflow</div>
            <div class="summary-value">Capture -> Review -> Confirm</div>
          </div>
          <div class="summary-stat">
            <div class="summary-label">Storage</div>
            <div class="summary-value">SQLite + Local Scan Files</div>
          </div>
          <div class="summary-stat">
            <div class="summary-label">History</div>
            <div class="summary-value">Live drawer on this page</div>
          </div>
        </aside>
      </section>
      <div class="guide">On iPhone Safari, tap Choose File first. Then pick Take Photo or Photo Library. After the photo is selected, tap Upload Selected Photo.</div>
      <section class="upload-card">
        <div class="upload-head">
          <div>
            <h2 class="upload-title">Upload From Phone</h2>
            <p class="upload-copy">Capture or choose an image, let the scanner resolve it, then confirm the add when the result looks right.</p>
          </div>
        </div>
        <form id="capture-form">
          <input
            id="photo-input"
            class="native-input"
            name="image"
            type="file"
            accept="image/*"
            capture="environment"
            required
          >
          <div id="file-name" class="file-name">No photo selected.</div>
          <button id="submit-button" type="submit" disabled>Upload Selected Photo</button>
        </form>
        <button id="confirm-button" class="secondary-button" type="button" disabled>Confirm / Add To Inventory</button>
      </section>
      <div id="status" class="status" data-tone="neutral">Ready.</div>
      <section class="results">
      <section class="result-section">
        <div class="section-header">
          <div>
            <h2 class="section-title">Latest Scan</h2>
            <p class="section-copy">This is the current working result from your most recent upload.</p>
          </div>
        </div>
        <div class="result-grid">
      <div class="result-card hero-card">
        <div class="result-label">Resolved Card</div>
        <div id="resolved-card-name" class="result-value emphasis"></div>
        <div id="resolved-card-printing" class="result-value"></div>
        <div class="badge-row">
          <div id="resolution-badge" class="badge">unresolved</div>
          <div id="match-badge" class="badge">none</div>
        </div>
      </div>
      <div class="result-card hero-card">
        <div class="result-label">Inventory Quantity</div>
        <div id="inventory-quantity" class="result-value emphasis">0</div>
        <div class="result-label" style="margin-top: 12px;">Last Add Status</div>
        <div id="add-status" class="result-value">Not added</div>
      </div>
      <div class="result-card">
        <div class="result-label">Used Image</div>
        <div id="used-image" class="result-value">None</div>
      </div>
      <div class="result-card">
        <div class="result-label">Detection Status</div>
        <div id="detection-status" class="result-value">failed</div>
      </div>
      <div class="result-card">
        <div class="result-label">Rectified Saved</div>
        <div id="rectified-saved" class="result-value">false</div>
      </div>
      <div class="result-card">
        <div class="result-label">Rectified Path</div>
        <div id="rectified-path" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Name</div>
        <div id="name-result" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Name Confidence</div>
        <div id="name-confidence" class="result-value">0.00</div>
      </div>
      <div class="result-card">
        <div class="result-label">Bottom Metadata OCR</div>
        <div id="metadata-result" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Metadata Confidence</div>
        <div id="metadata-confidence" class="result-value">0.00</div>
      </div>
      <div class="result-card">
        <div class="result-label">Printed Collector Text</div>
        <div id="printed-collector-text" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Collector Number</div>
        <div id="collector-result" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Rarity</div>
        <div id="rarity-result" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Set Code</div>
        <div id="set-code-result" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Language</div>
        <div id="lang-result" class="result-value"></div>
      </div>
      <div class="result-card">
        <div class="result-label">Overall Confidence</div>
        <div id="overall-confidence" class="result-value">0.00</div>
      </div>
      <div class="result-card">
        <div class="result-label">Resolution Status</div>
        <div id="resolution-status" class="result-value">Unresolved</div>
      </div>
      <div class="result-card">
        <div class="result-label">Match Type</div>
        <div id="match-type" class="result-value">None</div>
      </div>
        </div>
      </section>
      <section id="candidate-list" class="candidate-list" hidden>
        <div class="result-label">Review Candidates</div>
        <div id="candidate-options"></div>
      </section>
      </section>
    </main>
    <button id="history-toggle" class="history-tab" type="button" aria-expanded="false" aria-controls="history-drawer">Recent Scans</button>
    <aside id="history-drawer" class="history-drawer" aria-hidden="true">
      <div class="history-head">
        <div>
          <h2 class="history-title">Recent Scans</h2>
          <p class="history-subtitle">Your latest upload attempts and confirm actions.</p>
        </div>
        <button id="history-close" class="secondary-button small-button" type="button">Close</button>
      </div>
      <div id="history-list" class="history-list">
        <div class="history-empty">Loading...</div>
      </div>
    </aside>
  </div>
  <script>
    const form = document.getElementById("capture-form");
    const input = document.getElementById("photo-input");
    const button = document.getElementById("submit-button");
    const confirmButton = document.getElementById("confirm-button");
    const status = document.getElementById("status");
    const fileName = document.getElementById("file-name");
    const usedImage = document.getElementById("used-image");
    const detectionStatus = document.getElementById("detection-status");
    const rectifiedSaved = document.getElementById("rectified-saved");
    const rectifiedPath = document.getElementById("rectified-path");
    const nameResult = document.getElementById("name-result");
    const nameConfidence = document.getElementById("name-confidence");
    const metadataResult = document.getElementById("metadata-result");
    const metadataConfidence = document.getElementById("metadata-confidence");
    const printedCollectorText = document.getElementById("printed-collector-text");
    const collectorResult = document.getElementById("collector-result");
    const rarityResult = document.getElementById("rarity-result");
    const setCodeResult = document.getElementById("set-code-result");
    const langResult = document.getElementById("lang-result");
    const overallConfidence = document.getElementById("overall-confidence");
    const resolutionStatus = document.getElementById("resolution-status");
    const matchType = document.getElementById("match-type");
    const resolvedCardName = document.getElementById("resolved-card-name");
    const resolvedCardPrinting = document.getElementById("resolved-card-printing");
    const inventoryQuantity = document.getElementById("inventory-quantity");
    const addStatus = document.getElementById("add-status");
    const candidateList = document.getElementById("candidate-list");
    const candidateOptions = document.getElementById("candidate-options");
    const historyToggle = document.getElementById("history-toggle");
    const historyClose = document.getElementById("history-close");
    const historyDrawer = document.getElementById("history-drawer");
    const historyList = document.getElementById("history-list");
    const historyBackdrop = document.getElementById("history-backdrop");
    const resolutionBadge = document.getElementById("resolution-badge");
    const matchBadge = document.getElementById("match-badge");
    let latestResult = null;
    let selectedCandidateId = null;

    function statusTone(message) {
      const text = String(message || "").toLowerCase();
      if (text.includes("added") || text.includes("saved upload") || text === "ready.") {
        return "success";
      }
      if (text.includes("failed") || text.includes("error")) {
        return "danger";
      }
      if (text.includes("choose") || text.includes("selected") || text.includes("uploading") || text.includes("adding")) {
        return "warn";
      }
      return "neutral";
    }

    function updateStatus(message) {
      status.textContent = message;
      status.dataset.tone = statusTone(message);
    }

    function formatHistoryTime(value) {
      if (!value) {
        return "Unknown time";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      return date.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
      });
    }

    function historyLabel(item) {
      return item.ocr_name || item.resolved_scryfall_id || "Unknown card";
    }

    function historySetNumber(item) {
      const parts = [item.ocr_set_code, item.ocr_collector_number].filter(Boolean);
      return parts.length > 0 ? parts.join(" / ") : "No set/number";
    }

    function prettyStatus(value) {
      return String(value || "unknown").replaceAll("_", " ");
    }

    function setHistoryOpen(isOpen) {
      historyDrawer.classList.toggle("open", isOpen);
      historyDrawer.setAttribute("aria-hidden", String(!isOpen));
      historyToggle.setAttribute("aria-expanded", String(isOpen));
      historyBackdrop.classList.toggle("open", isOpen);
      historyBackdrop.hidden = !isOpen;
    }

    function renderHistory(items) {
      historyList.innerHTML = "";

      if (!items || items.length === 0) {
        historyList.innerHTML = '<div class="history-empty">No scans yet.</div>';
        return;
      }

      items.forEach((item) => {
        const card = document.createElement("article");
        card.className = "history-item";
        if (latestResult?.scan_event_id === item.id) {
          card.classList.add("active");
        }
        card.innerHTML = `
          <div class="history-item-title">${historyLabel(item)}</div>
          <div class="history-item-meta">${historySetNumber(item)}</div>
          <div class="history-item-meta">${formatHistoryTime(item.captured_at)}</div>
          <div class="history-badge ${item.status || ""}">${prettyStatus(item.status)}</div>
        `;
        historyList.appendChild(card);
      });
    }

    async function loadHistory() {
      historyList.innerHTML = '<div class="history-empty">Loading...</div>';
      try {
        const response = await fetch("/scan-history?limit=20");
        const data = await response.json();
        if (!response.ok) {
          historyList.innerHTML = '<div class="history-empty">Unable to load scan history.</div>';
          return;
        }
        renderHistory(data);
      } catch (error) {
        historyList.innerHTML = '<div class="history-empty">Unable to load scan history.</div>';
      }
    }

    function renderCandidates(data) {
      candidateOptions.innerHTML = "";
      selectedCandidateId = null;

      const needsReview = Boolean(data.resolution?.needs_review) || data.resolution?.status === "fallback_match";
      const candidates = data.resolution?.candidates || [];

      if (!needsReview || candidates.length === 0) {
        candidateList.hidden = true;
        return;
      }

      candidateList.hidden = false;

      candidates.forEach((candidate, index) => {
        const wrapper = document.createElement("label");
        wrapper.className = "candidate-option";

        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "candidate";
        radio.value = candidate.scryfall_id;
        radio.addEventListener("change", () => {
          selectedCandidateId = candidate.scryfall_id;
          confirmButton.disabled = false;
        });

        const text = document.createElement("span");
        text.textContent = `${candidate.name} (${candidate.set_code} / ${candidate.collector_number})`;

        wrapper.appendChild(radio);
        wrapper.appendChild(text);
        candidateOptions.appendChild(wrapper);

        if (index === 0) {
          radio.checked = true;
          selectedCandidateId = candidate.scryfall_id;
        }
      });
    }

    function setResults(data) {
      latestResult = data;
      selectedCandidateId = data.resolution?.card?.scryfall_id || null;
      usedImage.textContent = data.used_image_path || "None";
      detectionStatus.textContent = data.detection_status || "failed";
      rectifiedSaved.textContent = String(data.rectified_saved ?? false);
      rectifiedPath.textContent = data.rectified_path || "";
      nameResult.textContent = data.ocr?.name?.text || "";
      nameConfidence.textContent = (data.ocr?.name?.confidence ?? 0).toFixed(2);
      metadataResult.textContent = data.ocr?.bottom_metadata?.text || "";
      metadataConfidence.textContent = (data.ocr?.bottom_metadata?.confidence ?? 0).toFixed(2);
      printedCollectorText.textContent = data.metadata?.printed_collector_text || "";
      collectorResult.textContent = data.metadata?.collector_number || "";
      rarityResult.textContent = data.metadata?.rarity || "";
      setCodeResult.textContent = data.metadata?.set_code || "";
      langResult.textContent = data.metadata?.lang || "";
      overallConfidence.textContent = (data.ocr?.overall_confidence ?? 0).toFixed(2);
      resolutionStatus.textContent = data.resolution?.status || "unresolved";
      matchType.textContent = data.resolution?.match_type || "none";
      resolutionBadge.textContent = prettyStatus(data.resolution?.status || "unresolved");
      resolutionBadge.className = "badge";
      matchBadge.textContent = prettyStatus(data.resolution?.match_type || "none");
      matchBadge.className = "badge";
      if (data.resolution?.status === "exact_match") {
        resolutionBadge.classList.add("good");
      } else if (data.resolution?.status === "fallback_match") {
        resolutionBadge.classList.add("warn");
      } else {
        resolutionBadge.classList.add("danger");
      }
      resolvedCardName.textContent = data.resolution?.card?.name || "";
      if (data.resolution?.card) {
        resolvedCardPrinting.textContent = `${data.resolution.card.set_code} / ${data.resolution.card.collector_number}`;
      } else {
        resolvedCardPrinting.textContent = "";
      }
      inventoryQuantity.textContent = String(data.inventory?.quantity ?? 0);
      addStatus.textContent = data.inventory?.status || "Not added";
      renderCandidates(data);

      const isExact = data.resolution?.status === "exact_match";
      const needsReview = Boolean(data.resolution?.needs_review) || data.resolution?.status === "fallback_match";
      if (isExact) {
        confirmButton.disabled = !data.resolution?.card?.scryfall_id;
      } else if (needsReview) {
        confirmButton.disabled = !selectedCandidateId;
      } else {
        confirmButton.disabled = true;
      }
    }

    input.addEventListener("change", () => {
      if (!input.files || input.files.length === 0) {
        fileName.textContent = "No photo selected.";
        button.disabled = true;
        return;
      }

      fileName.textContent = `Selected: ${input.files[0].name}`;
      button.disabled = false;
      updateStatus("Photo selected. Tap upload to send it to your PC.");
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      if (!input.files || input.files.length === 0) {
        updateStatus("Choose a photo first.");
        return;
      }

      const formData = new FormData();
      formData.append("image", input.files[0]);

      button.disabled = true;
      updateStatus("Uploading...");

      try {
        const response = await fetch("/capture", {
          method: "POST",
          body: formData
        });

        const data = await response.json();
        if (!response.ok) {
          updateStatus(data.detail || "Upload failed.");
          return;
        }

        setResults(data);
        loadHistory();
        updateStatus(`Saved ${data.filename}\nPath: ${data.saved_path}\n${data.processing_status}`);
        form.reset();
        fileName.textContent = "No photo selected.";
        button.disabled = true;
      } catch (error) {
        updateStatus("Upload failed. Check that your phone and PC are on the same network.");
      } finally {
        if (input.files && input.files.length > 0) {
          button.disabled = false;
        }
      }
    });

    confirmButton.addEventListener("click", async () => {
      const needsReview = Boolean(latestResult?.resolution?.needs_review) || latestResult?.resolution?.status === "fallback_match";
      const scryfallId = needsReview ? selectedCandidateId : latestResult?.resolution?.card?.scryfall_id;
      if (!scryfallId) {
        addStatus.textContent = "No resolved card to add.";
        return;
      }

      confirmButton.disabled = true;
      addStatus.textContent = "Adding to inventory...";
      updateStatus("Adding to inventory...");

      try {
        const payload = {
          scan_event_id: latestResult.scan_event_id ?? null,
          scryfall_id: scryfallId,
          image_path: latestResult.used_image_path,
          ocr_name: latestResult.ocr?.name?.text || "",
          ocr_set_code: latestResult.metadata?.set_code || "",
          ocr_collector_number: latestResult.metadata?.collector_number || "",
          confidence: latestResult.ocr?.overall_confidence ?? 0
        };

        const response = await fetch("/confirm-add", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
          addStatus.textContent = data.detail || "Add failed.";
          updateStatus(data.detail || "Add failed.");
          return;
        }

        inventoryQuantity.textContent = String(data.quantity);
        addStatus.textContent = data.status;
        loadHistory();
        updateStatus(data.status);
      } catch (error) {
        addStatus.textContent = "Add failed.";
        updateStatus("Add failed.");
      } finally {
        const isExact = latestResult?.resolution?.status === "exact_match";
        if (isExact) {
          confirmButton.disabled = !latestResult?.resolution?.card?.scryfall_id;
        } else {
          confirmButton.disabled = !selectedCandidateId;
        }
      }
    });

    historyToggle.addEventListener("click", () => {
      const shouldOpen = !historyDrawer.classList.contains("open");
      setHistoryOpen(shouldOpen);
      if (shouldOpen) {
        loadHistory();
      }
    });

    historyClose.addEventListener("click", () => {
      setHistoryOpen(false);
    });

    historyBackdrop.addEventListener("click", () => {
      setHistoryOpen(false);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        setHistoryOpen(false);
      }
    });

    updateStatus("Ready.");
    loadHistory();
  </script>
</body>
</html>
        """.strip()
    )


@router.post("/capture")
async def capture_upload(image: UploadFile = File(...)) -> dict[str, object]:
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="No image data received.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large. Keep uploads under 20 MB.")

    try:
        with Image.open(BytesIO(payload)) as source_image:
            normalized = ImageOps.exif_transpose(source_image).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported image upload: {exc}") from exc

    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"raw_{timestamp}.jpg"
    raw_path = SCANS_DIR / filename
    normalized.save(raw_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    rectified_path = raw_path.with_name(raw_path.name.replace("raw_", "rectified_", 1))
    rectified_saved = False
    detection_status = "failed"

    if cv2 is not None:
        try:
            image_bgr = cv2.imread(str(raw_path))
            quad_points = detect_card_quad(image_bgr)
            if quad_points is not None:
                rectified_bgr = rectify_card(image_bgr, quad_points)
                if cv2.imwrite(str(rectified_path), rectified_bgr):
                    rectified_saved = True
                    detection_status = "ok"
        except Exception:
            detection_status = "failed"

    used_image_path = rectified_path if rectified_saved else raw_path
    ocr_source_image = "rectified" if rectified_saved else "raw"
    processing_status = (
        "Saved upload. Card detection and rectification succeeded; OCR used the rectified image."
        if rectified_saved
        else "Saved upload. Card detection failed; OCR used the raw image."
    )

    ocr_results: OCRResults = {}
    parsed_metadata = {
        "bottom_metadata_text": "",
        "bottom_metadata_confidence": 0.0,
        "printed_collector_text": "",
        "collector_number": "",
        "rarity": "",
        "set_code": "",
        "lang": "",
    }
    ocr_error = ocr_availability_message()
    if ocr_error is None:
        try:
            ocr_results = get_easyocr_reader().read_rois(used_image_path)
            parsed_metadata = extract_parsed_metadata(ocr_results)
            processing_status += " OCR complete."
        except Exception as exc:
            ocr_error = f"OCR failed: {exc}"
    else:
        processing_status += f" {ocr_error}"

    with SessionLocal() as session:
        resolution = resolve_card_printing(
            session,
            set_code=parsed_metadata.get("set_code"),
            collector_number=parsed_metadata.get("collector_number"),
            name=ocr_results.get("name_roi", ("", 0.0))[0],
            rarity=parsed_metadata.get("rarity"),
            lang=parsed_metadata.get("lang") or "en",
        )
        scan_event = ScanEvent(
            image_path=str(used_image_path),
            ocr_name=ocr_results.get("name_roi", ("", 0.0))[0] or None,
            ocr_set_code=parsed_metadata.get("set_code") or None,
            ocr_collector_number=parsed_metadata.get("collector_number") or None,
            confidence=overall_confidence(ocr_results),
            resolved_scryfall_id=((resolution.get("card") or {}).get("scryfall_id") if resolution.get("card") else None),
            status=capture_scan_status(resolution),
        )
        session.add(scan_event)
        session.commit()
        session.refresh(scan_event)

    return {
        "scan_event_id": scan_event.id,
        "filename": filename,
        "saved_path": str(raw_path),
        "timestamp": timestamp,
        "used_image_path": str(used_image_path),
        "rectified_saved": rectified_saved,
        "rectified_path": str(rectified_path) if rectified_saved else None,
        "detection_status": detection_status,
        "ocr_source_image": ocr_source_image,
        "processing_status": processing_status,
        "ocr_error": ocr_error,
        "metadata": {
            "bottom_metadata_text": parsed_metadata["bottom_metadata_text"],
            "printed_collector_text": parsed_metadata["printed_collector_text"],
            "collector_number": parsed_metadata["collector_number"],
            "rarity": parsed_metadata["rarity"],
            "set_code": parsed_metadata["set_code"],
            "lang": parsed_metadata["lang"],
        },
        "resolution": resolution,
        "inventory": {
            "quantity": 0,
            "status": "Not added",
        },
        "ocr": {
            "name": {
                "text": ocr_results.get("name_roi", ("", 0.0))[0],
                "confidence": ocr_results.get("name_roi", ("", 0.0))[1],
            },
            "bottom_metadata": {
                "text": ocr_results.get("bottom_metadata_roi", ("", 0.0))[0],
                "confidence": ocr_results.get("bottom_metadata_roi", ("", 0.0))[1],
            },
            "overall_confidence": overall_confidence(ocr_results),
        },
    }


@router.post("/confirm-add")
async def confirm_add(payload: ConfirmAddRequest) -> dict[str, object]:
    with SessionLocal() as session:
        card = session.execute(
            select(CardPrinting).where(CardPrinting.scryfall_id == payload.scryfall_id).limit(1)
        ).scalar_one_or_none()
        if card is None:
            raise HTTPException(status_code=404, detail="Resolved card was not found in the local catalog.")

        inventory_item = session.execute(
            select(InventoryItem).where(InventoryItem.card_printing_id == card.id).limit(1)
        ).scalar_one_or_none()

        if inventory_item is None:
            inventory_item = InventoryItem(card_printing_id=card.id, quantity=1)
            session.add(inventory_item)
        else:
            inventory_item.quantity += 1

        scan_event = None
        if payload.scan_event_id is not None:
            scan_event = session.execute(
                select(ScanEvent).where(ScanEvent.id == payload.scan_event_id).limit(1)
            ).scalar_one_or_none()

        if scan_event is None:
            scan_event = ScanEvent()
            session.add(scan_event)

        scan_event.image_path = payload.image_path
        scan_event.ocr_name = payload.ocr_name
        scan_event.ocr_set_code = payload.ocr_set_code
        scan_event.ocr_collector_number = payload.ocr_collector_number
        scan_event.confidence = payload.confidence
        scan_event.resolved_scryfall_id = payload.scryfall_id
        scan_event.status = "confirmed"

        session.commit()
        session.refresh(inventory_item)

        return {
            "status": f"Added {card.name}. Inventory quantity is now {inventory_item.quantity}.",
            "quantity": inventory_item.quantity,
            "scan_event_id": scan_event.id,
            "card": {
                "scryfall_id": card.scryfall_id,
                "name": card.name,
                "set_code": card.set_code,
                "collector_number": card.collector_number,
            },
        }
