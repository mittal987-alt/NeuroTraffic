"""
TrafficVision AI - Helmet Detection
------------------------------------------------
Uses a pretrained helmet-detection model hosted by Roboflow.
"""

import os
from inference_sdk import InferenceHTTPClient

ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "PASTE_YOUR_ROBOFLOW_API_KEY_HERE")
# Using a widely accessible public model
HELMET_MODEL_ID = "motorcycle-helmet-detection-ndpda/1"

_client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY,
)


def check_helmet(cropped_frame) -> str | None:
    """
    Runs helmet detection. Returns result or None silently on error.
    """
    if not ROBOFLOW_API_KEY or "PASTE_YOUR" in ROBOFLOW_API_KEY:
        return None

    try:
        result = _client.infer(cropped_frame, model_id=HELMET_MODEL_ID)
        predictions = result.get("predictions", [])
        if not predictions:
            return None

        # Take the highest-confidence prediction
        best = max(predictions, key=lambda p: p["confidence"])
        class_name = best["class"].lower()

        if "without" in class_name or "no" in class_name:
            return "without_helmet"
        elif "with" in class_name or "helmet" in class_name:
            return "with_helmet"
    except Exception:
        # Silently fail to avoid console spam
        return None
    return None
