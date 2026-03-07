from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image, ImageOps

from db.card_resolution import resolve_card_printing
from db.repo import SessionLocal
from ocr.easyocr_reader import OCRResults, get_easyocr_reader, ocr_availability_message

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
  </style>
</head>
<body>
  <main class="panel">
    <h1>MTG Phone Capture</h1>
    <p>Take a photo with your phone camera and upload it directly to your PC scanner.</p>
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
    <div id="status" class="status">Ready.</div>
    <section class="results">
      <div class="result-row">
        <div class="result-label">Used Image</div>
        <div id="used-image" class="result-value">None</div>
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
        <div class="result-label">Collector Number</div>
        <div id="collector-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Collector Confidence</div>
        <div id="collector-confidence" class="result-value">0.00</div>
      </div>
      <div class="result-row">
        <div class="result-label">Set Code</div>
        <div id="set-code-result" class="result-value"></div>
      </div>
      <div class="result-row">
        <div class="result-label">Set Code Confidence</div>
        <div id="set-code-confidence" class="result-value">0.00</div>
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
    </section>
  </main>
  <script>
    const form = document.getElementById("capture-form");
    const input = document.getElementById("photo-input");
    const button = document.getElementById("submit-button");
    const status = document.getElementById("status");
    const fileName = document.getElementById("file-name");
    const usedImage = document.getElementById("used-image");
    const nameResult = document.getElementById("name-result");
    const nameConfidence = document.getElementById("name-confidence");
    const collectorResult = document.getElementById("collector-result");
    const collectorConfidence = document.getElementById("collector-confidence");
    const setCodeResult = document.getElementById("set-code-result");
    const setCodeConfidence = document.getElementById("set-code-confidence");
    const overallConfidence = document.getElementById("overall-confidence");
    const resolutionStatus = document.getElementById("resolution-status");
    const matchType = document.getElementById("match-type");
    const resolvedCardName = document.getElementById("resolved-card-name");
    const resolvedCardPrinting = document.getElementById("resolved-card-printing");

    function setResults(data) {
      usedImage.textContent = data.used_image_path || "None";
      nameResult.textContent = data.ocr?.name?.text || "";
      nameConfidence.textContent = (data.ocr?.name?.confidence ?? 0).toFixed(2);
      collectorResult.textContent = data.ocr?.collector_number?.text || "";
      collectorConfidence.textContent = (data.ocr?.collector_number?.confidence ?? 0).toFixed(2);
      setCodeResult.textContent = data.ocr?.set_code?.text || "";
      setCodeConfidence.textContent = (data.ocr?.set_code?.confidence ?? 0).toFixed(2);
      overallConfidence.textContent = (data.ocr?.overall_confidence ?? 0).toFixed(2);
      resolutionStatus.textContent = data.resolution?.status || "unresolved";
      matchType.textContent = data.resolution?.match_type || "none";
      resolvedCardName.textContent = data.resolution?.card?.name || "";
      if (data.resolution?.card) {
        resolvedCardPrinting.textContent = `${data.resolution.card.set_code} / ${data.resolution.card.collector_number}`;
      } else {
        resolvedCardPrinting.textContent = "";
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

    used_image_path = preferred_ocr_image(raw_path)
    processing_status = "Saved upload. Rectified image not found; OCR used the raw image."
    if used_image_path != raw_path:
        processing_status = "Saved upload. OCR used the matching rectified image."

    ocr_results: OCRResults = {}
    ocr_error = ocr_availability_message()
    if ocr_error is None:
        try:
            ocr_results = get_easyocr_reader().read_rois(used_image_path)
            processing_status += " OCR complete."
        except Exception as exc:
            ocr_error = f"OCR failed: {exc}"
    else:
        processing_status += f" {ocr_error}"

    with SessionLocal() as session:
        resolution = resolve_card_printing(
            session,
            set_code=ocr_results.get("set_code_roi", ("", 0.0))[0],
            collector_number=ocr_results.get("collector_number_roi", ("", 0.0))[0],
            name=ocr_results.get("name_roi", ("", 0.0))[0],
            lang="en",
        )

    return {
        "filename": filename,
        "saved_path": str(raw_path),
        "timestamp": timestamp,
        "used_image_path": str(used_image_path),
        "processing_status": processing_status,
        "ocr_error": ocr_error,
        "resolution": resolution,
        "ocr": {
            "name": {
                "text": ocr_results.get("name_roi", ("", 0.0))[0],
                "confidence": ocr_results.get("name_roi", ("", 0.0))[1],
            },
            "collector_number": {
                "text": ocr_results.get("collector_number_roi", ("", 0.0))[0],
                "confidence": ocr_results.get("collector_number_roi", ("", 0.0))[1],
            },
            "set_code": {
                "text": ocr_results.get("set_code_roi", ("", 0.0))[0],
                "confidence": ocr_results.get("set_code_roi", ("", 0.0))[1],
            },
            "overall_confidence": overall_confidence(ocr_results),
        },
    }
