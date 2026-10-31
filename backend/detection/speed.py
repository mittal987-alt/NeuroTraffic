"""
TrafficVision AI - Speed estimation
------------------------------------------------
Calculates vehicle speed from position history and checks against the
configured speed limit, requiring N consecutive confirmations before alerting.
Supports homography transform from camera calibration points when available,
falling back to PIXELS_PER_METER. Uses real elapsed monotonic time.
"""

from collections import defaultdict, deque
import numpy as np
import cv2

from alerts import save_and_push_alert
from config import PIXELS_PER_METER, SPEED_LIMIT_KMH, CONSECUTIVE_VIOLATION_CHECKS

MIN_SAMPLES = 3

_overspeed_consecutive: dict[tuple[str, int], int] = defaultdict(int)


def calculate_speed_kmh(
    history: deque,
    fps: float | None = 30.0,
    homography_matrix: np.ndarray | None = None,
) -> float | None:
    """
    Estimates speed in km/h from a track's position history.
    History elements are tuples: (timestamp, cx, cy).
    Returns None if fewer than MIN_SAMPLES are present or elapsed time <= 0.
    """
    if len(history) < MIN_SAMPLES:
        return None

    t0, x0, y0 = history[0]
    t1, x1, y1 = history[-1]

    # Real elapsed seconds (history stores timestamp_seconds)
    time_elapsed = float(t1 - t0)
    if time_elapsed <= 0:
        return None

    # Calculate distance in meters using homography or PIXELS_PER_METER
    if homography_matrix is not None:
        try:
            pts = np.array([[[float(x0), float(y0)]], [[float(x1), float(y1)]]], dtype=np.float32)
            transformed = cv2.perspectiveTransform(pts, homography_matrix)
            mx0, my0 = transformed[0][0]
            mx1, my1 = transformed[1][0]
            meters_dist = ((mx1 - mx0) ** 2 + (my1 - my0) ** 2) ** 0.5
        except Exception:
            pixel_dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            meters_dist = pixel_dist / PIXELS_PER_METER
    else:
        pixel_dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        meters_dist = pixel_dist / PIXELS_PER_METER

    speed_kmh = (meters_dist / time_elapsed) * 3.6
    return round(float(speed_kmh), 1)


def check_overspeed(
    camera_id: str,
    track_id: int,
    vehicle_type: str,
    speed_kmh: float,
    frame=None,
    box=None,
):
    """
    Raises an alert if speed_kmh exceeds the speed limit in N consecutive checks.
    """
    key = (camera_id, track_id)
    if speed_kmh > SPEED_LIMIT_KMH:
        _overspeed_consecutive[key] += 1
        if _overspeed_consecutive[key] >= CONSECUTIVE_VIOLATION_CHECKS:
            from detection.plate import latest_detected_plates
            plate = latest_detected_plates.get((camera_id, track_id), "unknown")
            message_text = f"{vehicle_type.capitalize()} [{plate}] exceeded {SPEED_LIMIT_KMH:.0f} km/h ({speed_kmh:.0f} km/h)"
            save_and_push_alert(
                "overspeed",
                camera_id,
                track_id,
                message_text,
                speed_kmh=speed_kmh,
                frame=frame,
                box=box,
            )
    else:
        _overspeed_consecutive[key] = 0
