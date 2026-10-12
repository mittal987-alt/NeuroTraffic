"""
TrafficVision AI - Seat belt detection (integration layer)
------------------------------------------------
Same pattern as detection_helmet.py: dedup per (camera_id, track_id),
crop the vehicle, run the check in a background thread, alert if
violation found.
"""

import asyncio

from alerts import save_and_push_alert
from seatbelt_detection import check_seatbelt

seatbelt_checked_track_ids: set[tuple[str, int]] = set()


async def check_seatbelt_and_alert(camera_id: str, track_id: int, vehicle_type: str, frame, box):
    key = (camera_id, track_id)
    if key in seatbelt_checked_track_ids:
        return
    seatbelt_checked_track_ids.add(key)

    x1, y1, x2, y2 = map(int, box.xyxy[0])
    cropped = frame[max(y1, 0):y2, max(x1, 0):x2]
    if cropped.size == 0:
        return

    result = await asyncio.to_thread(check_seatbelt, cropped)

    if result == "without_seatbelt":
        from detection.plate import latest_detected_plates
        plate = latest_detected_plates.get((camera_id, track_id), "unknown")
        message_text = f"{vehicle_type.capitalize()} [{plate}] - seatbelt violation detected"
        save_and_push_alert("no_seatbelt", camera_id, track_id, message_text)