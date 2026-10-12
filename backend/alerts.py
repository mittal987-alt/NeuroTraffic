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
from datetime import datetime

from database import Alert, PlateRead, SessionLocal
from push_notifications import send_push_notification
from websocket_manager import broadcast
from config import TEST_DEVICE_TOKEN

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


def log_alert(
    db,
    alert_type: str,
    message: str,
    camera_id: str = "camera_1",
    track_id: int | None = None,
    speed_kmh: float | None = None,
    plate_text: str | None = None,
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
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    title = _ALERT_TITLES.get(alert_type, "Alert")
    if TEST_DEVICE_TOKEN != "PASTE_YOUR_FCM_TOKEN_HERE":
        send_push_notification(TEST_DEVICE_TOKEN, title, f"[{camera_id}] {message}")
    else:
        print(f"Mock push sent successfully: Notification(title='{title}', body='[{camera_id}] {message}') to PASTE_YOUR_FCM_TOKEN_HERE")

    return alert


def save_and_push_alert(alert_type: str, camera_id: str, track_id: int, message_text: str, speed_kmh: float | None = None):
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

    db = SessionLocal()
    try:
        alert = Alert(
            alert_type=alert_type,
            message=message_text,
            track_id=track_id,
            camera_id=camera_id,
            speed_kmh=speed_kmh,
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
            # Try to get the event loop. If we're in a worker thread (which we usually are
            # during detection), we need to handle it safely.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Fallback to finding any available loop or using the event loop policy
                loop = asyncio.get_event_loop()

            asyncio.run_coroutine_threadsafe(
                broadcast({
                    "type": "alert",
                    "id": alert.id,
                    "alert_type": alert.alert_type,
                    "message": alert.message,
                    "track_id": alert.track_id,
                    "camera_id": alert.camera_id,
                    "speed_kmh": alert.speed_kmh,
                    "status": alert.status,
                    "plate_text": plate_text,
                    "timestamp": alert.timestamp.isoformat(),
                }),
                loop
            )
        except Exception as e:
            print(f"[WebSocket Broadcast Failed] {e}")
    finally:
        db.close()

    title = _ALERT_TITLES.get(alert_type, "Alert")
    if TEST_DEVICE_TOKEN != "PASTE_YOUR_FCM_TOKEN_HERE":
        send_push_notification(TEST_DEVICE_TOKEN, title, f"[{camera_id}] {message_text}")
    else:
        print(f"Mock push sent successfully: Notification(title='{title}', body='[{camera_id}] {message_text}') to PASTE_YOUR_FCM_TOKEN_HERE")