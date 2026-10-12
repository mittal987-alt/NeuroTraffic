"""
TrafficVision AI - Lane detection
------------------------------------------------
Uses a pretrained semantic segmentation model hosted by Roboflow.
"""

import os
from inference_sdk import InferenceHTTPClient

ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "PASTE_YOUR_ROBOFLOW_API_KEY_HERE")
LANE_MODEL_ID = "lane-detection-real-world-dataset/1"

_client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY,
)


def get_lane_polygons(frame) -> list[list[tuple[float, float]]]:
    """
    Runs lane segmentation. Returns polygons or empty list silently on error.
    """
    if not ROBOFLOW_API_KEY or "PASTE_YOUR" in ROBOFLOW_API_KEY:
        return []

    try:
        result = _client.infer(frame, model_id=LANE_MODEL_ID)
        polygons = []
        for prediction in result.get("predictions", []):
            points = prediction.get("points", [])
            if points:
                polygons.append([(p["x"], p["y"]) for p in points])
        return polygons
    except Exception:
        # Silently fail to avoid console spam
        return []
