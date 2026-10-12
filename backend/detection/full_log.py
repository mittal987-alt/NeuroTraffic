"""
TrafficVision AI - Full detection logging
------------------------------------------------
Logs plate + speed + face together on every occurrence, throttled to
once every LOG_INTERVAL_FRAMES per vehicle (not truly every single
frame -- that would flood the database and re-run OCR/face-detection
far more than needed for a moving vehicle that hasn't changed much
frame to frame).
"""

import asyncio
import os
import uuid

import cv2

from database import DetectionLog, SessionLocal
from anpr import read_plate
from detection.face import detect_face_crop

LOG_INTERVAL_FRAMES = 15  # roughly every 0.5s at 30fps
FACE_IMAGE_DIR = "captured_faces"
os.makedirs(FACE_IMAGE_DIR, exist_ok=True)

_last_logged_frame: dict[tuple[str, int], int] = {}


async def log_full_detection(camera_id: str, track_id: int, frame_count: int, frame, box, speed_kmh: float | None):
    key = (camera_id, track_id)
    if frame_count - _last_logged_frame.get(key, -LOG_INTERVAL_FRAMES) < LOG_INTERVAL_FRAMES:
        return
    _last_logged_frame[key] = frame_count

    x1, y1, x2, y2 = map(int, box.xyxy[0])
    cropped = frame[max(y1, 0):y2, max(x1, 0):x2]
    if cropped.size == 0:
        return

    plate_result = await asyncio.to_thread(read_plate, cropped)
    plate_text = plate_result[0] if plate_result else None

    face_crop = await asyncio.to_thread(detect_face_crop, cropped)
    face_path = None
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