"""
TrafficVision AI - Emergency Vehicle Detection & Green Corridor Automation
----------------------------------------------------------------------------
Monitors vehicle detections and plate reads or visual cues to detect
Emergency Vehicles (Ambulance, Fire Engine, Police Squad).
When detected, automatically activates Green Corridor signal preemption.
"""

import time
import re
from database import SessionLocal
from alerts import log_alert
from signal_state import trigger_green_corridor, is_green_corridor_active
from websocket_manager import broadcast

# Emergency keyword matchers in ANPR or vehicle classification
EMERGENCY_KEYWORDS = {"AMBULANCE", "POLICE", "FIRE", "EMERGENCY", "RESCUE", "108", "102", "100", "112"}

# Cooldown per camera to prevent repetitive alerts for the same vehicle
_last_emergency_trigger: dict[str, float] = {}
COOLDOWN_SEC = 30.0


def is_emergency_match(text: str | None) -> bool:
    """
    Checks if text contains an exact emergency keyword using word/token boundaries.
    Prevents false substrings like '100' or '102' matching inside normal plates like 'MH12AB1002'.
    """
    if not text:
        return False
    upper = text.strip().upper()
    for k in EMERGENCY_KEYWORDS:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(k)}(?![A-Za-z0-9])"
        if re.search(pattern, upper):
            return True
    return False


def check_emergency_vehicle(
    camera_id: str,
    track_id: int,
    vehicle_type: str,
    plate_text: str | None = None,
    custom_label: str | None = None,
) -> bool:
    """
    Checks if vehicle qualifies as an emergency vehicle.
    If yes and cooldown elapsed, triggers Green Corridor and logs alert.
    """
    is_emergency = False
    vehicle_title = "Emergency Vehicle"

    if is_emergency_match(custom_label):
        is_emergency = True
        vehicle_title = custom_label.upper()

    if is_emergency_match(plate_text):
        is_emergency = True
        vehicle_title = f"Emergency Vehicle ({plate_text})"

    # If flagged as emergency
    if is_emergency:
        now = time.time()
        last_time = _last_emergency_trigger.get(camera_id, 0.0)

        if now - last_time > COOLDOWN_SEC:
            _last_emergency_trigger[camera_id] = now
            trigger_green_corridor(camera_id, duration_sec=25)

            # Log system alert
            db = SessionLocal()
            try:
                alert = log_alert(
                    db=db,
                    alert_type="emergency_vehicle",
                    message=f"🚑 {vehicle_title} detected! Green Corridor activated for {camera_id.upper()}.",
                    camera_id=camera_id,
                    track_id=track_id,
                    plate_text=plate_text,
                )
                # Broadcast live alert to connected WebSocket clients
                try:
                    import asyncio
                    payload = {
                        "type": "alert",
                        "id": alert.id,
                        "alert_type": "emergency_vehicle",
                        "message": alert.message,
                        "track_id": track_id,
                        "speed_kmh": None,
                        "camera_id": camera_id,
                        "status": "new",
                        "plate_text": plate_text,
                        "timestamp": alert.timestamp.isoformat(),
                        "green_corridor": True,
                    }
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(broadcast(payload), loop)
                except Exception as e:
                    print(f"[WebSocket Broadcast Failed] {e}")
            finally:
                db.close()

        return True

    return False
