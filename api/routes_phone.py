from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
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
    scryfall_id: str
    image_path: str | None = None
    ocr_name: str | None = None
    ocr_set_code: str | None = None
    ocr_collector_number: str | None = None
    confidence: float | None = None


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
      --bg: #f4efe7;
      --panel: #fffaf2;
      --ink: #1f1b16;
      --muted: #665f56;
      --accent: #1c7c54;
      --accent-strong: #11563a;
      --border: #d8cec0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top, rgba(28, 124, 84, 0.12), transparent 35%),
        linear-gradient(180deg, var(--bg), #efe6d8);
      color: var(--ink);
      display: grid;
      place-items: center;
      padding: 20px;
    }
    .panel {
      width: min(100%, 440px);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 16px 40px rgba(31, 27, 22, 0.12);
    }
    h1 {
      margin: 0 0 10px;
      font-size: 1.5rem;
    }
    p {
      margin: 0 0 16px;
      color: var(--muted);
      line-height: 1.45;
    }
    .guide {
      margin: 0 0 18px;
      padding: 14px;
      border: 1px dashed var(--border);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.6);
      color: var(--muted);
      font-size: 0.95rem;
    }
    .nav-link {
      display: inline-block;
      margin: 0 0 16px;
      color: var(--accent);
      font-weight: 600;
      text-decoration: none;
    }
    .native-input,
    button {
      width: 100%;
      border-radius: 12px;
      padding: 14px 16px;
      font-size: 1rem;
    }
    .native-input {
      margin-bottom: 12px;
      border: 1px solid var(--border);
      background: white;
    }
    button {
      border: 0;
      background: var(--accent);
      color: white;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled {
      background: #8fb5a3;
      cursor: default;
    }
    .secondary-button {
      margin-top: 12px;
      background: #243b2f;
    }
    .file-name {
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 0.95rem;
    }
    .status {
      margin-top: 16px;
      min-height: 24px;
      font-size: 0.95rem;
      color: var(--muted);
      white-space: pre-wrap;
    }
    .results {
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--border);
    }
    .result-row {
      margin-bottom: 10px;
    }
    .result-label {
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 4px;
    }
    .result-value {
      font-size: 1rem;
      color: var(--ink);
      word-break: break-word;
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
  </style>
</head>
<body>
  <main class="panel">
    <h1>MTG Phone Capture</h1>
    <p>Take a photo with your phone camera and upload it directly to your PC scanner.</p>
    <a class="nav-link" href="/inventory/view">View Inventory</a>
    <div class="guide">On iPhone Safari, tap Choose File first. Then pick Take Photo or Photo Library. After the photo is selected, tap Upload Selected Photo.</div>
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
    <div id="status" class="status">Ready.</div>
    <section class="results">
      <div class="result-row">
        <div class="result-label">Used Image</div>
        <div id="used-image" class="result-value">None</div>
      </div>
      <div class="result-row">
        <div class="result-label">Detection Status</div>
        <div id="detection-status" class="result-value">failed</div>
      </div>
      <div class="result-row">
        <div class="result-label">Rectified Saved</div>
        <div id="rectified-saved" class="result-value">false</div>
      </div>
      <div class="result-row">
        <div class="result-label">Rectified Path</div>
        <div id="rectified-path" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Name</div>
        <div id="name-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Name Confidence</div>
        <div id="name-confidence" class="result-value">0.00</div>
      </div>
      <div class="result-row">
        <div class="result-label">Bottom Metadata OCR</div>
        <div id="metadata-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Metadata Confidence</div>
        <div id="metadata-confidence" class="result-value">0.00</div>
      </div>
      <div class="result-row">
        <div class="result-label">Printed Collector Text</div>
        <div id="printed-collector-text" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Collector Number</div>
        <div id="collector-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Rarity</div>
        <div id="rarity-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Set Code</div>
        <div id="set-code-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Language</div>
        <div id="lang-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Overall Confidence</div>
        <div id="overall-confidence" class="result-value">0.00</div>
      </div>
      <div class="result-row">
        <div class="result-label">Resolution Status</div>
        <div id="resolution-status" class="result-value">Unresolved</div>
      </div>
      <div class="result-row">
        <div class="result-label">Match Type</div>
        <div id="match-type" class="result-value">None</div>
      </div>
      <div class="result-row">
        <div class="result-label">Resolved Card</div>
        <div id="resolved-card-name" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Resolved Set / Number</div>
        <div id="resolved-card-printing" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Inventory Quantity</div>
        <div id="inventory-quantity" class="result-value">0</div>
      </div>
      <div class="result-row">
        <div class="result-label">Last Add Status</div>
        <div id="add-status" class="result-value">Not added</div>
      </div>
      <section id="candidate-list" class="candidate-list" hidden>
        <div class="result-label">Review Candidates</div>
        <div id="candidate-options"></div>
      </section>
    </section>
  </main>
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
    let latestResult = null;
    let selectedCandidateId = null;

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
      status.textContent = "Photo selected. Tap upload to send it to your PC.";
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      if (!input.files || input.files.length === 0) {
        status.textContent = "Choose a photo first.";
        return;
      }

      const formData = new FormData();
      formData.append("image", input.files[0]);

      button.disabled = true;
      status.textContent = "Uploading...";

      try {
        const response = await fetch("/capture", {
          method: "POST",
          body: formData
        });

        const data = await response.json();
        if (!response.ok) {
          status.textContent = data.detail || "Upload failed.";
          return;
        }

        setResults(data);
        status.textContent = `Saved ${data.filename}\nPath: ${data.saved_path}\n${data.processing_status}`;
        form.reset();
        fileName.textContent = "No photo selected.";
        button.disabled = true;
      } catch (error) {
        status.textContent = "Upload failed. Check that your phone and PC are on the same network.";
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

      try {
        const payload = {
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
          return;
        }

        inventoryQuantity.textContent = String(data.quantity);
        addStatus.textContent = data.status;
      } catch (error) {
        addStatus.textContent = "Add failed.";
      } finally {
        const isExact = latestResult?.resolution?.status === "exact_match";
        if (isExact) {
          confirmButton.disabled = !latestResult?.resolution?.card?.scryfall_id;
        } else {
          confirmButton.disabled = !selectedCandidateId;
        }
      }
    });
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

    return {
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

        scan_event = ScanEvent(
            image_path=payload.image_path,
            ocr_name=payload.ocr_name,
            ocr_set_code=payload.ocr_set_code,
            ocr_collector_number=payload.ocr_collector_number,
            confidence=payload.confidence,
            resolved_scryfall_id=payload.scryfall_id,
            status="confirmed",
        )
        session.add(scan_event)
        session.commit()
        session.refresh(inventory_item)

        return {
            "status": f"Added {card.name}. Inventory quantity is now {inventory_item.quantity}.",
            "quantity": inventory_item.quantity,
            "card": {
                "scryfall_id": card.scryfall_id,
                "name": card.name,
                "set_code": card.set_code,
                "collector_number": card.collector_number,
            },
        }
