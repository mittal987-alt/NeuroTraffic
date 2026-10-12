"""
TrafficVision AI - Analytics queries
------------------------------------------------
Aggregation queries for the Analytics Dashboard: hourly traffic
trends and alert-type breakdowns. Kept separate from main.py so
route handlers stay thin.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import VehicleEvent, Alert


def get_hourly_traffic(db: Session, hours_back: int = 24):
    """
    Returns vehicle counts grouped by hour, for the last `hours_back`
    hours. Useful for spotting rush-hour patterns.

    Returns a list like:
        [{"hour": "2026-07-21T08:00:00", "count": 42}, ...]
    """
    rows = (
        db.query(
            func.date_trunc("hour", VehicleEvent.timestamp).label("hour"),
            func.count(VehicleEvent.id).label("count"),
        )
        .group_by("hour")
        .order_by("hour")
        .all()
    )
    return [{"hour": row.hour.isoformat(), "count": row.count} for row in rows]


def get_alert_breakdown(db: Session):
    """
    Returns alert counts grouped by type, e.g.:
        [{"alert_type": "overspeed", "count": 12}, {"alert_type": "wrong_way", "count": 3}]
    """
    rows = (
        db.query(Alert.alert_type, func.count(Alert.id).label("count"))
        .group_by(Alert.alert_type)
        .order_by(func.count(Alert.id).desc())
        .all()
    )
    return [{"alert_type": row.alert_type, "count": row.count} for row in rows]


def get_vehicle_type_breakdown(db: Session):
    """
    Returns vehicle counts grouped by type (car/motorcycle/bus/truck).
    Shaped as a list for easier charting on the Flutter side.
    """
    rows = (
        db.query(VehicleEvent.vehicle_type, func.count(VehicleEvent.id).label("count"))
        .group_by(VehicleEvent.vehicle_type)
        .order_by(func.count(VehicleEvent.id).desc())
        .all()
    )
    return [{"vehicle_type": row.vehicle_type, "count": row.count} for row in rows]