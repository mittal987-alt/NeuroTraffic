"""
TrafficVision AI - Pothole detection (integration layer)
------------------------------------------------
Runs pothole detection periodically on the full frame (expensive,
same pattern as lane detection) and logs new pothole sightings,
deduped by rough location so the same physical pothole isn't
reported every single frame it stays in view.
"""

import time

from database import PotholeReport, SessionLocal
from pothole_detection import detect_potholes

POTHOLE_CHECK_INTERVAL_SEC = 3.0
DEDUPE_DISTANCE_PX = 50  # potholes within this distance of a recent report are considered "the same one"

_last_check_time: dict[str, float] = {}
_recent_reports: dict[str, list[tuple[float, float, float]]] = {}  # camera_id -> [(x, y, timestamp), ...]


def _is_duplicate(camera_id: str, x: float, y: float) -> bool:
    now = time.time()
    recent = _recent_reports.setdefault(camera_id, [])
    # Drop anything older than 60s so the same spot can be re-reported
    # eventually (e.g. after the pothole is fixed and reappears, or to
    # avoid the list growing forever).
    recent[:] = [(rx, ry, rt) for (rx, ry, rt) in recent if now - rt < 60]

    for rx, ry, _ in recent:
        if ((x - rx) ** 2 + (y - ry) ** 2) ** 0.5 < DEDUPE_DISTANCE_PX:
            return True
    return False


def check_potholes(camera_id: str, frame):
    """Call once per frame; internally throttles to POTHOLE_CHECK_INTERVAL_SEC."""
    now = time.time()
    if now - _last_check_time.get(camera_id, 0) < POTHOLE_CHECK_INTERVAL_SEC:
        return
    _last_check_time[camera_id] = now

    detections = detect_potholes(frame)
    for det in detections:
        x, y = det.get("x"), det.get("y")
        if x is None or y is None:
            continue
        if _is_duplicate(camera_id, x, y):
            continue

        _recent_reports.setdefault(camera_id, []).append((x, y, now))

        db = SessionLocal()
        try:
            report = PotholeReport(
                camera_id=camera_id,
                confidence=det.get("confidence"),
                frame_x=x,
                frame_y=y,
            )
            db.add(report)
            db.commit()

            # Trigger a real-time alert for the app
            from alerts import save_and_push_alert
            save_and_push_alert(
                alert_type="pothole",
                camera_id=camera_id,
                track_id=0, # track_id 0 for non-vehicle specific alerts
                message_text=f"Pothole detected at coordinates ({x:.0f}, {y:.0f})"
            )
        finally:
            db.close()
        print(f"[{camera_id}] Pothole detected at ({x:.0f}, {y:.0f}), confidence {det.get('confidence', 0):.2f}")