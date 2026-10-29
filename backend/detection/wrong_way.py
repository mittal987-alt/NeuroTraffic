"""
TrafficVision AI - Wrong-way detection
------------------------------------------------
Compares a vehicle's overall movement direction against the
configured EXPECTED_DIRECTION and raises an alert if it's moving
meaningfully opposite for N consecutive checks.
"""

from collections import defaultdict, deque

from alerts import save_and_push_alert
from config import EXPECTED_DIRECTION, WRONG_WAY_MIN_DISPLACEMENT_PX, CONSECUTIVE_VIOLATION_CHECKS

_wrong_way_consecutive: dict[tuple[str, int], int] = defaultdict(int)


def check_wrong_way(
    camera_id: str,
    track_id: int,
    vehicle_type: str,
    history: deque,
    frame=None,
    box=None,
):
    """
    Checks if vehicle is driving against normal flow.
    Requires N consecutive checks opposite to EXPECTED_DIRECTION.
    """
    if len(history) < 2:
        return
    _, x0, y0 = history[0]
    _, x1, y1 = history[-1]
    dx, dy = x1 - x0, y1 - y0

    displacement = (dx ** 2 + dy ** 2) ** 0.5
    if displacement < WRONG_WAY_MIN_DISPLACEMENT_PX:
        return

    ex, ey = EXPECTED_DIRECTION
    dot = dx * ex + dy * ey

    key = (camera_id, track_id)
    if dot < 0:
        _wrong_way_consecutive[key] += 1
        if _wrong_way_consecutive[key] >= CONSECUTIVE_VIOLATION_CHECKS:
            from detection.plate import latest_detected_plates
            plate = latest_detected_plates.get((camera_id, track_id), "unknown")
            message_text = f"{vehicle_type.capitalize()} [{plate}] detected going the wrong way"
            save_and_push_alert("wrong_way", camera_id, track_id, message_text, frame=frame, box=box)
    else:
        _wrong_way_consecutive[key] = 0