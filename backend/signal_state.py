"""
TrafficVision AI - Traffic signal state & Emergency Green Corridor
-------------------------------------------------------------------
Supports three signal modes:
  - "simulated": cycle between RED and GREEN periodically (default)
  - "manual": controlled via admin POST /signals/{camera_id}/state
  - "api": read from external HTTP endpoint (SIGNAL_API_URL) with 1s cache & safe "green" fallback
Includes emergency preemption (Green Corridor) support for all modes.
"""

import time
import requests

from config import SIGNAL_MODE, SIGNAL_API_URL

RED_DURATION_SEC = 10
GREEN_DURATION_SEC = 10
CYCLE_LENGTH_SEC = RED_DURATION_SEC + GREEN_DURATION_SEC

# Tracks cycle start times, manual states, and active emergency corridor overrides per camera
_camera_start_times: dict[str, float] = {}
_corridor_overrides: dict[str, float] = {}  # camera_id -> expiration timestamp
_manual_states: dict[str, str] = {}         # camera_id -> "red" | "green"
_api_cache: dict[str, tuple[float, str]] = {}  # camera_id -> (timestamp, state)


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


def set_manual_signal_state(camera_id: str, state: str):
    """Sets signal state for manual mode ('red' or 'green')."""
    _manual_states[camera_id] = state.lower()


def _fetch_api_signal_state(camera_id: str) -> str:
    """
    Queries external signal API with 1-second cache.
    Falls back safely to 'green' on any error/timeout.
    """
    now = time.time()
    cached = _api_cache.get(camera_id)
    if cached and (now - cached[0] < 1.0):
        return cached[1]

    state = "green"
    if SIGNAL_API_URL:
        try:
            resp = requests.get(SIGNAL_API_URL, params={"camera_id": camera_id}, timeout=1.0)
            if resp.status_code == 200:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                raw_state = data.get("state", resp.text).strip().lower()
                state = "red" if "red" in raw_state else "green"
        except Exception as e:
            # Safe fallback: never issue false red-light alerts when external source is down
            state = "green"

    _api_cache[camera_id] = (now, state)
    return state


def get_signal_state(camera_id: str) -> str:
    """
    Returns 'red' or 'green' for the given camera's signal.
    Emergency corridor always forces 'green'.
    """
    if is_green_corridor_active(camera_id):
        return "green"

    mode = SIGNAL_MODE.lower()
    if mode == "manual":
        return _manual_states.get(camera_id, "green")
    elif mode == "api":
        return _fetch_api_signal_state(camera_id)

    # Default: "simulated" cycle
    if camera_id not in _camera_start_times:
        _camera_start_times[camera_id] = time.time()

    elapsed = time.time() - _camera_start_times[camera_id]
    position_in_cycle = elapsed % CYCLE_LENGTH_SEC

    return "red" if position_in_cycle < RED_DURATION_SEC else "green"


def get_signal_info(camera_id: str) -> dict:
    """Returns comprehensive signal state and emergency preemption status."""
    active_corridor = is_green_corridor_active(camera_id)
    remaining_corridor = max(0.0, _corridor_overrides.get(camera_id, 0.0) - time.time()) if active_corridor else 0.0
    current_state = "green" if active_corridor else get_signal_state(camera_id)

    return {
        "camera_id": camera_id,
        "state": current_state,
        "is_emergency_corridor": active_corridor,
        "corridor_remaining_sec": round(remaining_corridor, 1),
    }