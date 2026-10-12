"""
TrafficVision AI - Simulated traffic signal state & Emergency Green Corridor
-----------------------------------------------------------------------------
Simulates traffic signal cycles between RED and GREEN, with emergency
preemption (Green Corridor) support for emergency vehicles like ambulances,
fire trucks, and police units.
"""

import time

RED_DURATION_SEC = 10
GREEN_DURATION_SEC = 10
CYCLE_LENGTH_SEC = RED_DURATION_SEC + GREEN_DURATION_SEC

# Tracks cycle start times and active emergency corridor overrides per camera
_camera_start_times: dict[str, float] = {}
_corridor_overrides: dict[str, float] = {}  # camera_id -> expiration timestamp


def trigger_green_corridor(camera_id: str, duration_sec: int = 20) -> dict:
    """
    Overrides the traffic signal to GREEN for emergency vehicle passage.
    """
    now = time.time()
    _corridor_overrides[camera_id] = now + duration_sec
    return {
        "camera_id": camera_id,
        "is_emergency_corridor": True,
        "duration_sec": duration_sec,
        "expires_at": _corridor_overrides[camera_id],
    }


def is_green_corridor_active(camera_id: str) -> bool:
    """Checks if green corridor preemption is currently active."""
    expiry = _corridor_overrides.get(camera_id, 0.0)
    return time.time() < expiry


def get_signal_state(camera_id: str) -> str:
    """
    Returns 'red' or 'green' for the given camera's signal.
    Emergency corridor always forces 'green'.
    """
    if is_green_corridor_active(camera_id):
        return "green"

    if camera_id not in _camera_start_times:
        _camera_start_times[camera_id] = time.time()

    elapsed = time.time() - _camera_start_times[camera_id]
    position_in_cycle = elapsed % CYCLE_LENGTH_SEC

    return "red" if position_in_cycle < RED_DURATION_SEC else "green"


def get_signal_info(camera_id: str) -> dict:
    """Returns comprehensive signal state and emergency preemption status."""
    active_corridor = is_green_corridor_active(camera_id)
    remaining_corridor = max(0.0, _corridor_overrides.get(camera_id, 0.0) - time.time()) if active_corridor else 0.0

    return {
        "camera_id": camera_id,
        "state": "green" if active_corridor else get_signal_state(camera_id),
        "is_emergency_corridor": active_corridor,
        "corridor_remaining_sec": round(remaining_corridor, 1),
    }