"""
TrafficVision AI - Accident detection (heuristic, temporal)
------------------------------------------------
Unlike other checks in this project, this one reasons about CHANGE
OVER TIME, not a single frame. It flags a possible accident when a
tracked vehicle both:
  1. Decelerates suddenly (large speed drop vs. its recent history)
  2. AND its bounding box significantly overlaps another vehicle's

HONEST LIMITATION: this is a heuristic approximation, not a trained
temporal model (e.g. a real CNN+LSTM). It will have false positives
(e.g. a car braking hard right as another car happens to be nearby)
and false negatives (e.g. low-speed collisions, or accidents outside
frame). Treat flagged events as "worth a human looking at," not
confirmed accidents.
"""

from collections import defaultdict, deque

from alerts import save_and_push_alert

SPEED_DROP_THRESHOLD_KMH = 25.0  # a drop of at least this much between consecutive readings looks like a crash, not normal braking
OVERLAP_THRESHOLD = 0.15          # fraction of box area that must overlap to count as "colliding"
SPEED_HISTORY_LENGTH = 5           # how many recent speed readings to keep per vehicle

# Per-camera, per-track_id recent speed readings (for detecting sudden drops)
_speed_history: dict[tuple[str, int], deque] = defaultdict(lambda: deque(maxlen=SPEED_HISTORY_LENGTH))

accident_alerted_track_ids: set[tuple[str, int]] = set()

def cleanup_old_tracks(active_track_ids: set[int], camera_id: str):
    """
    Clears memory for vehicles that have left the camera's view.
    Prevents the _speed_history and alert sets from growing forever.
    """
    # Clean up speed history
    keys_to_remove = [k for k in _speed_history.keys() if k[0] == camera_id and k[1] not in active_track_ids]
    for k in keys_to_remove:
        del _speed_history[k]

    # Clean up alerted IDs (optional: keep them for a while to avoid re-alerting immediately if they re-enter)
    alert_keys_to_remove = [k for k in accident_alerted_track_ids if k[0] == camera_id and k[1] not in active_track_ids]
    for k in alert_keys_to_remove:
        accident_alerted_track_ids.discard(k)


def _box_overlap_fraction(box_a, box_b) -> float:
    """
    Returns the overlap area as a fraction of the smaller box's area.
    box_a, box_b are (x1, y1, x2, y2) tuples.
    """
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0  # no overlap

    intersection_area = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    smaller_area = min(area_a, area_b)
    if smaller_area <= 0:
        return 0.0

    return intersection_area / smaller_area


def record_speed(camera_id: str, track_id: int, speed_kmh: float):
    """Call this whenever a fresh speed reading is available for a vehicle."""
    _speed_history[(camera_id, track_id)].append(speed_kmh)


def check_sudden_deceleration(camera_id: str, track_id: int) -> bool:
    """Returns True if this vehicle's speed just dropped sharply."""
    history = _speed_history[(camera_id, track_id)]
    if len(history) < 2:
        return False
    previous, current = history[-2], history[-1]
    return (previous - current) >= SPEED_DROP_THRESHOLD_KMH


def check_accident(camera_id: str, vehicles_this_frame: list[dict]):
    """
    Call once per frame with the full list of vehicles currently in
    view (each needs: track_id, vehicle_type, box as (x1,y1,x2,y2),
    speed_kmh). Checks every pair for the deceleration+overlap
    combination.
    """
    for i, vehicle_a in enumerate(vehicles_this_frame):
        track_id_a = vehicle_a["track_id"]
        key_a = (camera_id, track_id_a)
        if key_a in accident_alerted_track_ids:
            continue
        if not check_sudden_deceleration(camera_id, track_id_a):
            continue

        for vehicle_b in vehicles_this_frame:
            if vehicle_b["track_id"] == track_id_a:
                continue

            overlap = _box_overlap_fraction(vehicle_a["box"], vehicle_b["box"])
            if overlap >= OVERLAP_THRESHOLD:
                accident_alerted_track_ids.add(key_a)

                # Fetch plates for both vehicles if available
                from detection.plate import latest_detected_plates
                plate_a = latest_detected_plates.get((camera_id, track_id_a), "unknown")
                plate_b = latest_detected_plates.get((camera_id, vehicle_b["track_id"]), "unknown")

                message_text = (
                    f"Possible collision: {vehicle_a['vehicle_type']} [{plate_a}] "
                    f"and {vehicle_b['vehicle_type']} [{plate_b}] -- "
                    f"sudden deceleration + overlap detected"
                )
                save_and_push_alert("accident", camera_id, track_id_a, message_text)
                break