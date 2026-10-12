"""
TrafficVision AI - Emergency Vehicle Detection & Green Corridor Automation
----------------------------------------------------------------------------
Monitors vehicle detections and plate reads or visual cues to detect
Emergency Vehicles (Ambulance, Fire Engine, Police Squad).
When detected, automatically activates Green Corridor signal preemption.
"""

import time
from database import SessionLocal
from alerts import log_alert
from signal_state import trigger_green_corridor, is_green_corridor_active
from websocket_manager import broadcast

# Emergency keyword matchers in ANPR or vehicle classification
EMERGENCY_KEYWORDS = {"AMBULANCE", "POLICE", "FIRE", "EMERGENCY", "RESCUE", "108", "102", "100", "112"}

# Cooldown per camera to prevent repetitive alerts for the same vehicle
_last_emergency_trigger: dict[str, float] = {}
COOLDOWN_SEC = 30.0


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

    if custom_label and any(k in custom_label.upper() for k in EMERGENCY_KEYWORDS):
        is_emergency = True
        vehicle_title = custom_label.upper()

    if plate_text:
        upper_plate = plate_text.upper()
        if any(k in upper_plate for k in EMERGENCY_KEYWORDS):
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
                        "status": "active",
                        "plate_text": plate_text,
                        "timestamp": alert.timestamp.isoformat(),
                        "green_corridor": True,
                    }
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = asyncio.get_event_loop()
                    asyncio.run_coroutine_threadsafe(broadcast(payload), loop)
                except Exception as e:
                    print(f"[WebSocket Broadcast Failed] {e}")
            finally:
                db.close()

        return True

    return False
