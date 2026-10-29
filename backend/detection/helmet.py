"""
TrafficVision AI - Helmet detection (integration layer)
------------------------------------------------
Wraps the Roboflow-based check_helmet() function with consecutive check
confirmation and alert saving. Requires N consecutive checks of 'without_helmet'
before saving an alert.
"""

from collections import defaultdict
import asyncio

from alerts import save_and_push_alert
from helmet_detection import check_helmet
from config import CONSECUTIVE_VIOLATION_CHECKS

helmet_checked_track_ids: set[tuple[str, int]] = set()
_helmet_consecutive: dict[tuple[str, int], int] = defaultdict(int)


async def check_helmet_and_alert(camera_id: str, track_id: int, frame, box):
    """
    Crops the motorcycle region from the frame and checks it for a
    helmet via the Roboflow API. Requires N consecutive violation checks.
    """
    key = (camera_id, track_id)
    if key in helmet_checked_track_ids:
        return

    if hasattr(box, "xyxy"):
        x1, y1, x2, y2 = map(int, box.xyxy[0])
    elif isinstance(box, (tuple, list)) and len(box) == 4:
        x1, y1, x2, y2 = map(int, box)
    else:
        return

    h, w = frame.shape[:2]
    cropped = frame[max(y1, 0):min(y2, h), max(x1, 0):min(x2, w)]
    if cropped is None or cropped.size == 0:
        return

    result = await asyncio.to_thread(check_helmet, cropped)

    if result == "without_helmet":
        _helmet_consecutive[key] += 1
        if _helmet_consecutive[key] >= CONSECUTIVE_VIOLATION_CHECKS:
            helmet_checked_track_ids.add(key)
            from detection.plate import latest_detected_plates
            plate = latest_detected_plates.get((camera_id, track_id), "unknown")
            message_text = f"Motorcycle [{plate}] rider detected without a helmet"
            save_and_push_alert("no_helmet", camera_id, track_id, message_text, frame=frame, box=box)
    elif result == "with_helmet":
        _helmet_consecutive[key] = 0
        helmet_checked_track_ids.add(key)