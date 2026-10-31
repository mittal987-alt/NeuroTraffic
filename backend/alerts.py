"""
TrafficVision AI - Alert handling
------------------------------------------------
Shared logic for saving an alert to the database and sending a push
notification. Every detection type (overspeed, wrong-way, no-helmet,
no-seatbelt, red-light, lane-departure, accident) calls into this
same function so the dedupe/save/push behavior stays consistent
across all of them.
"""

import asyncio
import os
import uuid
from datetime import datetime

import cv2

from database import Alert, PlateRead, SessionLocal
from push_notifications import send_push_notification
from websocket_manager import broadcast
from config import TEST_DEVICE_TOKEN

VIOLATIONS_DIR = "violations"
os.makedirs(VIOLATIONS_DIR, exist_ok=True)

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop

# Prevents sending a push every single frame a vehicle triggers a
# condition -- once per (alert_type, track_id) is enough.
alerted_track_ids: dict[str, set[tuple[str, int]]] = {
    "overspeed": set(),
    "wrong_way": set(),
    "no_helmet": set(),
    "no_seatbelt": set(),
    "red_light": set(),
    "lane_departure": set(),
    "accident": set(),
    "pothole": set(),
    "emergency_vehicle": set(),
}

_ALERT_TITLES = {
    "overspeed": "Overspeed Alert",
    "wrong_way": "Wrong-Way Alert",
    "no_helmet": "No Helmet Alert",
    "no_seatbelt": "No Seatbelt Alert",
    "red_light": "Red Light Alert",
    "lane_departure": "Lane Departure Alert",
    "accident": "Possible Accident Alert",
    "pothole": "Pothole Detected",
    "emergency_vehicle": "Emergency Vehicle Alert",
}


def _save_evidence_crop(frame, box) -> str | None:
    """Extracts a clean crop of the violating vehicle and saves to violations/."""
    try:
        if frame is None or box is None:
            return None
        if hasattr(box, "xyxy"):
            x1, y1, x2, y2 = map(int, box.xyxy[0])
        elif isinstance(box, (tuple, list)) and len(box) == 4:
            x1, y1, x2, y2 = map(int, box)
        else:
            return None

        h, w = frame.shape[:2]
        crop = frame[max(y1, 0):min(y2, h), max(x1, 0):min(x2, w)]
        if crop is None or crop.size == 0:
            return None

        filename = f"{VIOLATIONS_DIR}/{uuid.uuid4().hex}.jpg"
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            loop.run_in_executor(None, cv2.imwrite, filename, crop)
        else:
            cv2.imwrite(filename, crop)
        return filename
    except Exception as e:
        print(f"[Evidence Crop Failed] {e}")
        return None


def log_alert(
    db,
    alert_type: str,
    message: str,
    camera_id: str = "camera_1",
    track_id: int | None = None,
    speed_kmh: float | None = None,
    plate_text: str | None = None,
    evidence_path: str | None = None,
) -> Alert:
    """
    Creates and commits an Alert record to the database and sends a push notification.
    """
    alert = Alert(
        alert_type=alert_type,
        message=message,
        track_id=track_id,
        camera_id=camera_id,
        speed_kmh=speed_kmh,
        evidence_path=evidence_path,
        status="new",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    title = _ALERT_TITLES.get(alert_type, "Alert")
    def _do_push_log():
        if TEST_DEVICE_TOKEN != "PASTE_YOUR_FCM_TOKEN_HERE":
            send_push_notification(TEST_DEVICE_TOKEN, title, f"[{camera_id}] {message}")
        else:
            print(f"Mock push sent successfully: Notification(title='{title}', body='[{camera_id}] {message}') to PASTE_YOUR_FCM_TOKEN_HERE")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.run_in_executor(None, _do_push_log)
    elif _main_loop and _main_loop.is_running():
        _main_loop.run_in_executor(None, _do_push_log)
    else:
        _do_push_log()

    return alert


def save_and_push_alert(
    alert_type: str,
    camera_id: str,
    track_id: int,
    message_text: str,
    speed_kmh: float | None = None,
    frame=None,
    box=None,
    evidence_path: str | None = None,
):
    """
    Saves an Alert row to the database and sends a push notification.
    Uses track_id for vehicle deduplication, but allows multiple alerts
    for location-based events like potholes.
    """
    seen = alerted_track_ids.get(alert_type)
    if seen is None:
        return

    # Deduplicate by track_id, but NOT for potholes (track_id 0)
    # as potholes are deduplicated by coordinates in pothole.py
    if alert_type != "pothole":
        key = (camera_id, track_id)
        if key in seen:
            return
        seen.add(key)

    # Save evidence photo if available and not yet saved
    if evidence_path is None and frame is not None and box is not None:
        evidence_path = _save_evidence_crop(frame, box)

    db = SessionLocal()
    try:
        alert = Alert(
            alert_type=alert_type,
            message=message_text,
            track_id=track_id,
            camera_id=camera_id,
            speed_kmh=speed_kmh,
            evidence_path=evidence_path,
            status="new",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        # Try to find the latest license plate for this vehicle
        plate_text = None
        if track_id and track_id != 0:
            # 1. First check the live in-memory cache (fastest)
            from detection.plate import latest_detected_plates
            plate_text = latest_detected_plates.get((camera_id, track_id))

            # 2. Fallback to database if not in cache
            if not plate_text:
                plate = db.query(PlateRead).filter(
                    PlateRead.camera_id == camera_id,
                    PlateRead.track_id == track_id
                ).order_by(PlateRead.timestamp.desc()).first()
                if plate:
                    plate_text = plate.plate_text

        # Broadcast the alert to Flutter app via WebSocket
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            payload = {
                "type": "alert",
                "id": alert.id,
                "alert_type": alert.alert_type,
                "message": alert.message,
                "track_id": alert.track_id,
                "camera_id": alert.camera_id,
                "speed_kmh": alert.speed_kmh,
                "status": alert.status,
                "plate_text": plate_text,
                "evidence_path": alert.evidence_path,
                "timestamp": alert.timestamp.isoformat(),
            }

            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast(payload), loop)
            elif _main_loop and _main_loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast(payload), _main_loop)
        except Exception as e:
            print(f"[WebSocket Broadcast Failed] {e}")
    finally:
        db.close()

    def _do_push():
        title = _ALERT_TITLES.get(alert_type, "Alert")
        if TEST_DEVICE_TOKEN != "PASTE_YOUR_FCM_TOKEN_HERE":
            send_push_notification(TEST_DEVICE_TOKEN, title, f"[{camera_id}] {message_text}")
        else:
            print(f"Mock push sent successfully: Notification(title='{title}', body='[{camera_id}] {message_text}') to PASTE_YOUR_FCM_TOKEN_HERE")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running() and hasattr(loop, "run_in_executor"):
        loop.run_in_executor(None, _do_push)
    elif _main_loop and _main_loop.is_running() and hasattr(_main_loop, "run_in_executor"):
        _main_loop.run_in_executor(None, _do_push)
    else:
        _do_push()