"""
TrafficVision AI - Red-light violation detection
------------------------------------------------
A vehicle crossing the counting line while the signal is red counts as
a violation. Reuses the same crossing detection already in the pipeline
-- this just adds a signal-state check on top.
"""

from alerts import save_and_push_alert
from signal_state import get_signal_state

red_light_alerted_track_ids: set[tuple[str, int]] = set()


def check_red_light_violation(camera_id: str, track_id: int, vehicle_type: str, frame=None, box=None):
    """
    Call this at the moment a vehicle crosses the counting line
    (same moment save_crossing_event fires). Checks the current
    signal state and raises an alert if it's red.
    """
    key = (camera_id, track_id)
    if key in red_light_alerted_track_ids:
        return

    current_state = get_signal_state(camera_id)
    if current_state == "red":
        red_light_alerted_track_ids.add(key)
        from detection.plate import latest_detected_plates
        plate = latest_detected_plates.get((camera_id, track_id), "unknown")
        message_text = f"{vehicle_type.capitalize()} [{plate}] ran a red light (signal state: {current_state})"
        save_and_push_alert("red_light", camera_id, track_id, message_text, frame=frame, box=box)
