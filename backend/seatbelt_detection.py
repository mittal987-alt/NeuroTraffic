"""
TrafficVision AI - Seat belt detection
------------------------------------------------
Uses a pretrained seatbelt-detection model hosted by Roboflow.
"""

import os
from inference_sdk import InferenceHTTPClient

ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "PASTE_YOUR_ROBOFLOW_API_KEY_HERE")
# Using a model that is more likely to be accessible or handling failure gracefully
SEATBELT_MODEL_ID = "occupant-detection-4iuzv/1"

_client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY,
)


def check_seatbelt(cropped_frame) -> str | None:
    """
    Runs seatbelt detection. Returns result or None silently on error.
    """
    if not ROBOFLOW_API_KEY or "PASTE_YOUR" in ROBOFLOW_API_KEY:
        return None

    try:
        result = _client.infer(cropped_frame, model_id=SEATBELT_MODEL_ID)
        predictions = result.get("predictions", [])
        if not predictions:
            return None

        # Take the highest-confidence prediction from this crop
        best = max(predictions, key=lambda p: p["confidence"])
        class_name = best["class"].lower()

        if "no" in class_name or "without" in class_name:
            return "without_seatbelt"
        elif "seatbelt" in class_name or "with" in class_name:
            return "with_seatbelt"
    except Exception:
        # Silently fail to avoid console spam if model is down or ID changes
        return None
    return None
