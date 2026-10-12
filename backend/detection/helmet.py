
"""
TrafficVision AI - Helmet detection (integration layer)
------------------------------------------------
Wraps the raw Roboflow-based check_helmet() function (in
helmet_detection.py) with dedup tracking and alert saving, so the
main detection loop just calls one async function per motorcycle.
"""

import asyncio

from alerts import save_and_push_alert
from helmet_detection import check_helmet

# Tracks which (camera_id, track_id) pairs we've already sent for a
# helmet check (regardless of result) -- avoids repeated API calls.
helmet_checked_track_ids: set[tuple[str, int]] = set()


async def check_helmet_and_alert(camera_id: str, track_id: int, frame, box):
    """
    Crops the motorcycle region from the frame and checks it for a
    helmet via the Roboflow API. Caller is responsible for running
    this inside asyncio.create_task() so it doesn't block the loop.
    Only checked once per (camera_id, track_id).
    """
    key = (camera_id, track_id)
    if key in helmet_checked_track_ids:
        return
    helmet_checked_track_ids.add(key)

    x1, y1, x2, y2 = map(int, box.xyxy[0])
    cropped = frame[max(y1, 0):y2, max(x1, 0):x2]
    if cropped.size == 0:
        return

    result = await asyncio.to_thread(check_helmet, cropped)

    if result == "without_helmet":
        from detection.plate import latest_detected_plates
        plate = latest_detected_plates.get((camera_id, track_id), "unknown")
        message_text = f"Motorcycle [{plate}] rider detected without a helmet"
        save_and_push_alert("no_helmet", camera_id, track_id, message_text)