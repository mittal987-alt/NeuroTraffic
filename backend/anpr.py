"""
TrafficVision AI - ANPR (Automatic Number Plate Recognition)
------------------------------------------------------------------
Reads license plate text using EasyOCR on cropped vehicle images.

IMPORTANT LIMITATION (be upfront about this): we don't have a dedicated
plate-LOCATION model here, so we run OCR on the lower portion of the
whole vehicle crop (where plates usually sit) rather than a precisely
localized plate region. This means:
  - Works reasonably for clear, close-up, front/rear-facing shots
  - Struggles with angled views, small/distant vehicles, low light
  - False reads are common -- always treat results as "best guess",
    not ground truth, until you add a proper plate detector later.

Setup:
    pip install easyocr
    (first run downloads OCR model weights automatically, ~100MB)
"""

import re
import threading
import easyocr

# 'en' works reasonably for most Latin-alphabet plates.
_reader = easyocr.Reader(["en"], gpu=False)
_ocr_lock = threading.Lock()

# Plates are short, uppercase alphanumeric strings.
_PLATE_PATTERN = re.compile(r"^[A-Z0-9]{4,10}$")


def read_plate(cropped_frame) -> tuple[str, float] | None:
    """
    Runs OCR on a cropped vehicle image. Uses a lock to ensure
    thread-safety when multiple cameras call OCR at once.
    """
    height = cropped_frame.shape[0]
    lower_region = cropped_frame[int(height * 0.5):, :]

    if lower_region.size == 0:
        return None

    try:
        with _ocr_lock:
            results = _reader.readtext(lower_region)
    except Exception as e:
        print(f"ANPR OCR failed: {e}")
        return None

    best_match = None
    best_confidence = 0.0

    for (_bbox, text, confidence) in results:
        cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
        if _PLATE_PATTERN.match(cleaned) and confidence > best_confidence:
            best_match = cleaned
            best_confidence = confidence

    if best_match:
        return best_match, best_confidence
    return None