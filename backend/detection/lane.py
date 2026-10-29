"""
TrafficVision AI - Lane departure detection (integration layer)
------------------------------------------------
Runs lane segmentation periodically (not every frame -- expensive)
and checks whether each vehicle's center point falls within any
detected lane region. Requires N consecutive checks outside the marked
lanes before saving an alert.
"""

from collections import defaultdict
import time

from alerts import save_and_push_alert
from lane_detection import get_lane_polygons
from config import CONSECUTIVE_VIOLATION_CHECKS

LANE_CHECK_INTERVAL_SEC = 2.0

# Per-camera cache: last computed lane polygons + when they were computed
_lane_cache: dict[str, tuple[float, list]] = {}
lane_departure_alerted_track_ids: set[tuple[str, int]] = set()
_lane_consecutive: dict[tuple[str, int], int] = defaultdict(int)


def cleanup_old_lane_tracks(active_track_ids: set[int], camera_id: str):
    """Clears memory for vehicles that have left the camera's view."""
    keys_to_remove = [k for k in lane_departure_alerted_track_ids if k[0] == camera_id and k[1] not in active_track_ids]
    for k in keys_to_remove:
        lane_departure_alerted_track_ids.discard(k)
        _lane_consecutive.pop(k, None)


def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Standard ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    px, py = polygon[0]
    for i in range(1, n + 1):
        qx, qy = polygon[i % n]
        if ((py > y) != (qy > y)) and (x < (qx - px) * (y - py) / (qy - py + 1e-9) + px):
            inside = not inside
        px, py = qx, qy
    return inside


def get_current_lane_polygons(camera_id: str, frame):
    """Returns cached lane polygons, refreshing them if the cache is stale."""
    now = time.time()
    cached = _lane_cache.get(camera_id)
    if cached and (now - cached[0]) < LANE_CHECK_INTERVAL_SEC:
        return cached[1]

    polygons = get_lane_polygons(frame)
    _lane_cache[camera_id] = (now, polygons)
    return polygons


def check_lane_departure(
    camera_id: str,
    track_id: int,
    vehicle_type: str,
    cx: float,
    cy: float,
    polygons: list,
    frame=None,
    box=None,
):
    """Flags a vehicle whose center point isn't inside any known lane polygon after N consecutive checks."""
    if not polygons:
        return

    key = (camera_id, track_id)
    if key in lane_departure_alerted_track_ids:
        return

    inside_any_lane = any(_point_in_polygon(cx, cy, poly) for poly in polygons)
    if not inside_any_lane:
        _lane_consecutive[key] += 1
        if _lane_consecutive[key] >= CONSECUTIVE_VIOLATION_CHECKS:
            lane_departure_alerted_track_ids.add(key)
            from detection.plate import latest_detected_plates
            plate = latest_detected_plates.get((camera_id, track_id), "unknown")
            message_text = f"{vehicle_type.capitalize()} [{plate}] detected outside marked lane"
            save_and_push_alert("lane_departure", camera_id, track_id, message_text, frame=frame, box=box)
    else:
        _lane_consecutive[key] = 0