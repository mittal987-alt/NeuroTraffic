"""
TrafficVision AI - Speed estimation
------------------------------------------------
Calculates a vehicle's speed from its position history and checks it
against the configured speed limit, raising an alert if exceeded.
No database access here -- that's handled separately in
detection/pipeline.py (crossing events) and alerts.py (alert rows).
"""

from collections import deque

from alerts import save_and_push_alert
from config import PIXELS_PER_METER, SPEED_LIMIT_KMH


def calculate_speed_kmh(history: deque, fps: float) -> float | None:
    """
    Estimates speed in km/h from a track's position history.
    Returns None if there isn't enough history yet to estimate.
    """
    if len(history) < 2:
        return None

    f0, x0, y0 = history[0]
    f1, x1, y1 = history[-1]
    frame_gap = f1 - f0
    if frame_gap <= 0:
        return None

    pixel_dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    seconds_elapsed = frame_gap / fps
    speed_kmh = (pixel_dist / PIXELS_PER_METER / seconds_elapsed) * 3.6
    return round(speed_kmh, 1)


def check_overspeed(camera_id: str, track_id: int, vehicle_type: str, speed_kmh: float):
    """Raises an alert if speed_kmh exceeds the configured limit."""
    if speed_kmh > SPEED_LIMIT_KMH:
        from detection.plate import latest_detected_plates
        plate = latest_detected_plates.get((camera_id, track_id), "unknown")
        message_text = f"{vehicle_type.capitalize()} [{plate}] exceeded {SPEED_LIMIT_KMH:.0f} km/h ({speed_kmh:.0f} km/h)"
        save_and_push_alert("overspeed", camera_id, track_id, message_text, speed_kmh=speed_kmh)
