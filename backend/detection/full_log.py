"""
TrafficVision AI - Full detection logging
------------------------------------------------
Logs plate + speed + face together on every occurrence.
- Face capture is opt-in via ENABLE_FACE_CAPTURE (default False).
- Throttled to once every 2 seconds per track to avoid database bloat.
- Skips OCR if plate is already known in latest_detected_plates cache.
- Provides retention job to purge captured faces and rows older than FACE_RETENTION_DAYS.
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import cv2

from database import DetectionLog, SessionLocal
from anpr import read_plate
from detection.face import detect_face_crop
from config import ENABLE_FACE_CAPTURE, FACE_RETENTION_DAYS

FACE_IMAGE_DIR = "captured_faces"
os.makedirs(FACE_IMAGE_DIR, exist_ok=True)

_last_logged_time: dict[tuple[str, int], float] = {}


def cleanup_old_face_data():
    """
    Retention job: deletes captured_faces/ files and DetectionLog rows
    older than FACE_RETENTION_DAYS (default 7 days).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=FACE_RETENTION_DAYS)
    cutoff_ts = time.time() - (FACE_RETENTION_DAYS * 86400)

    db = SessionLocal()
    try:
        old_logs = db.query(DetectionLog).filter(DetectionLog.timestamp < cutoff).all()
        for log in old_logs:
            if log.face_image_path and os.path.exists(log.face_image_path):
                try:
                    os.remove(log.face_image_path)
                except OSError:
                    pass
            db.delete(log)
        db.commit()

        # Clean orphaned or old files in FACE_IMAGE_DIR directly
        if os.path.exists(FACE_IMAGE_DIR):
            for fname in os.listdir(FACE_IMAGE_DIR):
                fpath = os.path.join(FACE_IMAGE_DIR, fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff_ts:
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
    except Exception as e:
        print(f"[Retention Cleanup Warning] {e}")
    finally:
        db.close()


async def log_full_detection(camera_id: str, track_id: int, frame_count: int, frame, box, speed_kmh: float | None):
    """
    Logs detection event with plate, speed, and optional face crop.
    Throttled to once every 2.0 seconds per track.
    """
    key = (camera_id, track_id)
    now = time.monotonic()
    if now - _last_logged_time.get(key, 0.0) < 2.0:
        return
    _last_logged_time[key] = now

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

    # Skip OCR if the plate is already cached in latest_detected_plates
    from detection.plate import latest_detected_plates
    cached_plate = latest_detected_plates.get((camera_id, track_id))
    if cached_plate:
        plate_text = cached_plate
    else:
        plate_result = await asyncio.to_thread(read_plate, cropped)
        plate_text = plate_result[0] if plate_result else None

    # Face capture is strictly opt-in via ENABLE_FACE_CAPTURE
    face_path = None
    if ENABLE_FACE_CAPTURE:
        face_crop = await asyncio.to_thread(detect_face_crop, cropped)
        if face_crop is not None and face_crop.size > 0:
            filename = f"{FACE_IMAGE_DIR}/{uuid.uuid4().hex}.jpg"
            cv2.imwrite(filename, face_crop)
            face_path = filename

    db = SessionLocal()
    try:
        log = DetectionLog(
            track_id=track_id,
            camera_id=camera_id,
            plate_text=plate_text,
            speed_kmh=speed_kmh,
            face_image_path=face_path,
        )
        db.add(log)
        db.commit()
    finally:
        db.close()