"""
TrafficVision AI - Seat belt detection (integration layer)
------------------------------------------------
Wraps check_seatbelt() with consecutive check confirmation and alert saving.
Requires N consecutive checks of 'without_seatbelt' before saving an alert.
"""

from collections import defaultdict
import asyncio

from alerts import save_and_push_alert
from seatbelt_detection import check_seatbelt
from config import CONSECUTIVE_VIOLATION_CHECKS

seatbelt_checked_track_ids: set[tuple[str, int]] = set()
_seatbelt_consecutive: dict[tuple[str, int], int] = defaultdict(int)


async def check_seatbelt_and_alert(camera_id: str, track_id: int, vehicle_type: str, frame, box):
    key = (camera_id, track_id)
    if key in seatbelt_checked_track_ids:
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

    result = await asyncio.to_thread(check_seatbelt, cropped)

    if result == "without_seatbelt":
        _seatbelt_consecutive[key] += 1
        if _seatbelt_consecutive[key] >= CONSECUTIVE_VIOLATION_CHECKS:
            seatbelt_checked_track_ids.add(key)
            from detection.plate import latest_detected_plates
            plate = latest_detected_plates.get((camera_id, track_id), "unknown")
            message_text = f"{vehicle_type.capitalize()} [{plate}] - seatbelt violation detected"
            save_and_push_alert("no_seatbelt", camera_id, track_id, message_text, frame=frame, box=box)
    elif result == "with_seatbelt":
        _seatbelt_consecutive[key] = 0
        seatbelt_checked_track_ids.add(key)