"""
TrafficVision AI - Seat belt detection (integration layer)
------------------------------------------------
Wraps check_seatbelt() with consecutive check confirmation and alert saving.
Requires N consecutive checks of 'without_seatbelt' before saving an alert.

Improvements:
- CONFIRM_INTERVAL_SEC: minimum seconds between API calls per track
- _in_flight: skip if an API call is already running for this track
- MAX_API_ATTEMPTS: give up after N attempts to avoid infinite API calls
- None results: do not count as violation and do not reset the counter
"""

import asyncio
import time
from collections import defaultdict

from alerts import save_and_push_alert
from seatbelt_detection import check_seatbelt
from config import CONSECUTIVE_VIOLATION_CHECKS, CONFIRM_INTERVAL_SEC, MAX_API_ATTEMPTS

seatbelt_checked_track_ids: set[tuple[str, int]] = set()
_seatbelt_consecutive: dict[tuple[str, int], int] = defaultdict(int)
_seatbelt_last_check: dict[tuple[str, int], float] = {}
_seatbelt_in_flight: set[tuple[str, int]] = set()
_seatbelt_attempts: dict[tuple[str, int], int] = defaultdict(int)


async def check_seatbelt_and_alert(camera_id: str, track_id: int, vehicle_type: str, frame, box):
    """
    Crops the vehicle region from the frame and checks it for a seatbelt
    via the Roboflow API. Requires N consecutive violation checks.

    - Enforces CONFIRM_INTERVAL_SEC between calls per track.
    - Skips if an in-flight call for this track is already running.
    - Skips after MAX_API_ATTEMPTS regardless of result.
    - None API result: does not count as violation, does not reset counter.
    """
    key = (camera_id, track_id)
    if key in seatbelt_checked_track_ids:
        return

    # Attempt cap
    if _seatbelt_attempts[key] >= MAX_API_ATTEMPTS:
        return

    # Rate-limit: enforce minimum interval between calls
    now = time.monotonic()
    if now - _seatbelt_last_check.get(key, 0.0) < CONFIRM_INTERVAL_SEC:
        return

    # Skip if already in flight for this track
    if key in _seatbelt_in_flight:
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

    _seatbelt_in_flight.add(key)
    _seatbelt_last_check[key] = now
    _seatbelt_attempts[key] += 1
    try:
        result = await asyncio.to_thread(check_seatbelt, cropped)
    finally:
        _seatbelt_in_flight.discard(key)

    if result is None:
        # Inconclusive: do not count as violation, do not reset counter
        return

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
        _seatbelt_attempts[key] = 0
        seatbelt_checked_track_ids.add(key)