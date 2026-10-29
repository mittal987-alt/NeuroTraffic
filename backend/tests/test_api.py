"""
TrafficVision AI - Test Suite
-----------------------------
Tests for authentication, route protection, challan PDF generation, CSV exports,
emergency keyword matching, speed estimation, and consecutive-frame confirmation.
"""

from collections import deque
import io
import time
import pytest
from datetime import datetime, timezone

from database import User, Alert, PlateRead, VehicleEvent, Camera
from auth import hash_password, create_access_token
from detection.emergency import is_emergency_match
from detection.speed import calculate_speed_kmh, check_overspeed, MIN_SAMPLES
from detection.wrong_way import check_wrong_way
from detection.helmet import check_helmet_and_alert
import alerts


# ============================================================================
# 1. Signup / Login & Rate Limiting Tests
# ============================================================================

def test_signup_and_first_user_admin(client, db_session):
    resp = client.post("/auth/signup", json={
        "email": "first@trafficvision.ai",
        "name": "First Admin",
        "password": "securepassword123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["role"] == "admin"

    # Second user should default to "viewer"
    resp2 = client.post("/auth/signup", json={
        "email": "second@trafficvision.ai",
        "name": "Second User",
        "password": "securepassword123",
    })
    assert resp2.status_code == 200
    assert resp2.json()["user"]["role"] == "viewer"


def test_login_success_and_rate_limiting(client, db_session):
    from main import _login_failures
    _login_failures.clear()

    # Create test user
    user = User(
        email="operator@trafficvision.ai",
        name="Operator",
        password_hash=hash_password("correctpass123"),
        role="viewer",
    )
    db_session.add(user)
    db_session.commit()

    # 4 failed attempts should return 401
    for _ in range(4):
        resp = client.post("/auth/login", json={
            "email": "operator@trafficvision.ai",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    # 5th failed attempt triggers rate limit threshold
    resp5 = client.post("/auth/login", json={
        "email": "operator@trafficvision.ai",
        "password": "wrongpassword",
    })
    assert resp5.status_code == 401

    # 6th attempt should be blocked by rate limit with 429
    resp6 = client.post("/auth/login", json={
        "email": "operator@trafficvision.ai",
        "password": "correctpass123",
    })
    assert resp6.status_code == 429
    assert "Too many failed login attempts" in resp6.json()["detail"]


# ============================================================================
# 2. Protected Routes & Authorization Tests
# ============================================================================

def test_protected_routes_require_auth(client, db_session):
    protected_urls = [
        "/alerts",
        "/plates",
        "/events",
        "/potholes",
        "/cameras",
        "/density",
        "/analytics/hourly",
        "/analytics/alerts",
        "/analytics/vehicle_types",
        "/alerts/1/challan",
        "/stream/camera_1",
    ]
    for url in protected_urls:
        resp = client.get(url)
        assert resp.status_code == 401, f"{url} should require authentication"


def test_admin_authorization(client, db_session):
    # Viewer user
    viewer = User(
        email="viewer@test.com",
        name="Viewer",
        password_hash=hash_password("pass123"),
        role="viewer",
    )
    # Admin user
    admin = User(
        email="admin@test.com",
        name="Admin",
        password_hash=hash_password("pass123"),
        role="admin",
    )
    db_session.add_all([viewer, admin])
    db_session.commit()

    viewer_token = create_access_token(viewer.id, viewer.email)
    admin_token = create_access_token(admin.id, admin.email)

    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    admin_endpoints = [
        ("GET", "/logs"),
        ("GET", "/export/alerts.csv"),
        ("GET", "/export/events.csv"),
        ("POST", "/signals/camera_1/green_corridor"),
        ("POST", "/signals/camera_1/state", {"state": "red"}),
    ]

    for method, path, *payload in admin_endpoints:
        json_body = payload[0] if payload else None
        # Viewer should be forbidden (403)
        if method == "GET":
            r_viewer = client.get(path, headers=viewer_headers)
            r_admin = client.get(path, headers=admin_headers)
        else:
            r_viewer = client.post(path, json=json_body, headers=viewer_headers)
            r_admin = client.post(path, json=json_body, headers=admin_headers)

        assert r_viewer.status_code == 403, f"{path} should forbid non-admin"
        assert r_admin.status_code == 200, f"{path} should succeed for admin"


# ============================================================================
# 3. Challan Generation & Status Flow Tests
# ============================================================================

def test_challan_generation_and_status_flow(client, db_session):
    admin = User(email="admin_challan@test.com", name="Admin", password_hash=hash_password("p"), role="admin")
    db_session.add(admin)
    db_session.commit()
    token = create_access_token(admin.id, admin.email)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Alert in 'new' status cannot generate challan
    alert = Alert(
        alert_type="overspeed",
        message="Speed violation clocked",
        track_id=101,
        speed_kmh=95.0,
        camera_id="camera_1",
        status="new",
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    resp_new = client.get(f"/alerts/{alert.id}/challan", headers=headers)
    assert resp_new.status_code == 400
    assert "reviewed" in resp_new.json()["detail"]

    # 2. Non-violation types like pothole or emergency_vehicle must be refused
    pothole_alert = Alert(alert_type="pothole", message="Pothole detected", status="reviewed")
    db_session.add(pothole_alert)
    db_session.commit()
    db_session.refresh(pothole_alert)
    resp_pothole = client.get(f"/alerts/{pothole_alert.id}/challan", headers=headers)
    assert resp_pothole.status_code == 400
    assert "non-violation" in resp_pothole.json()["detail"]

    # 3. Add plate in PlateRead table
    plate_read = PlateRead(camera_id="camera_1", track_id=101, plate_text="DL01AB1234")
    db_session.add(plate_read)

    # 4. Human-in-the-loop review
    resp_resolve = client.post(
        f"/alerts/{alert.id}/resolve",
        json={"status": "reviewed", "resolution_notes": "Confirmed by officer #42"},
        headers=headers,
    )
    assert resp_resolve.status_code == 200
    assert resp_resolve.json()["status"] == "reviewed"

    # 5. Challan generation succeeds and updates status to 'challan_issued'
    resp_challan = client.get(f"/alerts/{alert.id}/challan", headers=headers)
    assert resp_challan.status_code == 200
    assert resp_challan.headers["content-type"] == "application/pdf"
    content = resp_challan.content
    assert content.startswith(b"%PDF")

    db_session.refresh(alert)
    assert alert.status == "challan_issued"


# ============================================================================
# 4. CSV Export Tests
# ============================================================================

def test_csv_exports(client, db_session):
    admin = User(email="admin_csv@test.com", name="Admin", password_hash=hash_password("p"), role="admin")
    alert = Alert(alert_type="wrong_way", message="Wrong way driving", track_id=202, camera_id="camera_1", status="new")
    event = VehicleEvent(track_id=202, vehicle_type="car", speed_kmh=45.0, camera_id="camera_1")
    plate = PlateRead(camera_id="camera_1", track_id=202, plate_text="KA05MJ9999")
    db_session.add_all([admin, alert, event, plate])
    db_session.commit()

    token = create_access_token(admin.id, admin.email)
    headers = {"Authorization": f"Bearer {token}"}

    # Test alerts CSV
    resp_alerts = client.get("/export/alerts.csv", headers=headers)
    assert resp_alerts.status_code == 200
    assert "KA05MJ9999" in resp_alerts.text
    assert "Wrong way driving" in resp_alerts.text

    # Test events CSV
    resp_events = client.get("/export/events.csv", headers=headers)
    assert resp_events.status_code == 200
    assert "KA05MJ9999" in resp_events.text
    assert "car" in resp_events.text


# ============================================================================
# 5. Emergency Keyword Matching Tests
# ============================================================================

def test_emergency_keyword_matching():
    # Ordinary plates containing substring '100' or '102' must NOT match
    assert not is_emergency_match("MH12AB1002")
    assert not is_emergency_match("DL04C1005")
    assert not is_emergency_match("KA011029")

    # True emergency identifiers must match
    assert is_emergency_match("108")
    assert is_emergency_match("AMBULANCE")
    assert is_emergency_match("POLICE")
    assert is_emergency_match("FIRE")
    assert is_emergency_match("DL-01-AMBULANCE")
    assert is_emergency_match("EMERGENCY 108")


# ============================================================================
# 6. Speed Calculation with MIN_SAMPLES & Calibration
# ============================================================================

def test_speed_calculation_min_samples():
    # History with fewer than MIN_SAMPLES (3) must return None
    short_history = deque([(1.0, 100, 100), (1.5, 120, 120)])
    assert calculate_speed_kmh(short_history) is None

    # History with >= MIN_SAMPLES returns valid float speed
    valid_history = deque([(1.0, 100, 100), (1.5, 120, 120), (2.0, 140, 140)])
    speed = calculate_speed_kmh(valid_history)
    assert speed is not None
    assert speed > 0


# ============================================================================
# 7. Consecutive-Frame Confirmation Logic Tests
# ============================================================================

def test_consecutive_violation_confirmation(db_session):
    from detection.speed import _overspeed_consecutive
    from detection.wrong_way import _wrong_way_consecutive
    _overspeed_consecutive.clear()
    _wrong_way_consecutive.clear()
    alerts.alerted_track_ids["overspeed"].clear()
    alerts.alerted_track_ids["wrong_way"].clear()

    cam = "camera_test"
    track = 888

    # Overspeed: checks 1 and 2 do NOT alert; check 3 triggers alert
    check_overspeed(cam, track, "car", 120.0)
    assert (cam, track) not in alerts.alerted_track_ids["overspeed"]

    check_overspeed(cam, track, "car", 125.0)
    assert (cam, track) not in alerts.alerted_track_ids["overspeed"]

    check_overspeed(cam, track, "car", 122.0)
    assert (cam, track) in alerts.alerted_track_ids["overspeed"]

    # Wrong-way: checks 1 and 2 do NOT alert; check 3 triggers alert
    track_ww = 999
    # Moving opposite: dy = -50 against normal (0, 1)
    rev_history = deque([(1.0, 200, 300), (2.0, 200, 250)])

    check_wrong_way(cam, track_ww, "car", rev_history)
    assert (cam, track_ww) not in alerts.alerted_track_ids["wrong_way"]

    check_wrong_way(cam, track_ww, "car", rev_history)
    assert (cam, track_ww) not in alerts.alerted_track_ids["wrong_way"]

    check_wrong_way(cam, track_ww, "car", rev_history)
    assert (cam, track_ww) in alerts.alerted_track_ids["wrong_way"]
