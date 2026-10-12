"""
TrafficVision AI - Pothole detection
------------------------------------------------
Uses a pretrained pothole-detection model hosted by Roboflow.
"""

import os
from inference_sdk import InferenceHTTPClient

ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "PASTE_YOUR_ROBOFLOW_API_KEY_HERE")
# Verified public model ID
POTHOLE_MODEL_ID = "pothole-v3/1"

_client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY,
)


def detect_potholes(frame) -> list[dict]:
    """
    Runs pothole detection. Returns detections or empty list silently on error.
    """
    if not ROBOFLOW_API_KEY or "PASTE_YOUR" in ROBOFLOW_API_KEY:
        return []

    try:
        result = _client.infer(frame, model_id=POTHOLE_MODEL_ID)
        return result.get("predictions", [])
    except Exception:
        # Silently fail to avoid console spam
        return []
