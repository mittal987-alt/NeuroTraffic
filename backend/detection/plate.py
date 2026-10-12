"""
TrafficVision AI - ANPR (integration layer)
------------------------------------------------
Wraps the raw OCR-based read_plate() function (in anpr.py) with dedup
tracking and database saving, so the main detection loop just calls
one async function per car/truck/bus.
"""

import asyncio

from database import PlateRead, SessionLocal
from anpr import read_plate

# Tracks how many times we've tried to read a plate for a vehicle
plate_check_counts: dict[tuple[str, int], int] = {}
MAX_PLATE_ATTEMPTS = 5

# Shared cache for the video pipeline to show plates on the live feed
latest_detected_plates: dict[tuple[str, int], str] = {}


def cleanup_old_plates(active_track_ids: set[int], camera_id: str):
    """Clears cached plates for vehicles that have left the view."""
    keys_to_remove = [k for k in latest_detected_plates.keys() if k[0] == camera_id and k[1] not in active_track_ids]
    for k in keys_to_remove:
        del latest_detected_plates[k]

    # Also clean up attempt counts
    count_keys_to_remove = [k for k in plate_check_counts.keys() if k[0] == camera_id and k[1] not in active_track_ids]
    for k in count_keys_to_remove:
        del plate_check_counts[k]


async def check_plate_and_save(camera_id: str, track_id: int, frame, box):
    """
    Crops the vehicle region and attempts an OCR plate read.
    Retries up to MAX_PLATE_ATTEMPTS until a valid plate is found.
    """
    key = (camera_id, track_id)

    # If we already have a plate for this vehicle, don't waste CPU
    if key in latest_detected_plates:
        return

    # Limit attempts to prevent infinite OCR on blurry/distant objects
    attempts = plate_check_counts.get(key, 0)
    if attempts >= MAX_PLATE_ATTEMPTS:
        return
    plate_check_counts[key] = attempts + 1

    x1, y1, x2, y2 = map(int, box.xyxy[0])
    cropped = frame[max(y1, 0):y2, max(x1, 0):x2]
    if cropped.size == 0:
        return

    result = await asyncio.to_thread(read_plate, cropped)
    if result is None:
        return

    plate_text, confidence = result

    # Only save if confidence is reasonable
    if confidence > 0.4:
        # Update cache for live video overlay
        latest_detected_plates[key] = plate_text

        db = SessionLocal()
        try:
            record = PlateRead(
                track_id=track_id,
                plate_text=plate_text,
                confidence=float(confidence),
                camera_id=camera_id,
            )
            db.add(record)
            db.commit()
        finally:
            db.close()
        print(f"Plate read: {plate_text} (confidence {confidence:.2f}) for {camera_id}, track {track_id}")
