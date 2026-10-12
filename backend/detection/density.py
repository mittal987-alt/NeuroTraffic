"""
TrafficVision AI - Traffic density
------------------------------------------------
No model needed -- density is just a function of how many vehicles
are visible in the current frame. Thresholds are illustrative; tune
them once you see real numbers from your footage.
"""

# Tune these based on your camera's typical vehicle counts per frame.
# These are reasonable starting points, not universal truths.
DENSITY_THRESHOLDS = {
    "low": 5,       # 0-5 vehicles visible = Low
    "medium": 12,    # 6-12 = Medium
    "high": 20,       # 13-20 = High
    # anything above = Very High
}


def calculate_density(vehicle_count: int) -> dict:
    """
    Returns a dict like {"level": "medium", "color": "yellow", "count": 8}
    based on how many vehicles are visible in the current frame.
    """
    if vehicle_count <= DENSITY_THRESHOLDS["low"]:
        level, color = "low", "green"
    elif vehicle_count <= DENSITY_THRESHOLDS["medium"]:
        level, color = "medium", "yellow"
    elif vehicle_count <= DENSITY_THRESHOLDS["high"]:
        level, color = "high", "orange"
    else:
        level, color = "very_high", "red"

    return {"level": level, "color": color, "count": vehicle_count}