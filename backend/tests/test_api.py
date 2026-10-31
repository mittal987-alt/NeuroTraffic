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

def test_signup_admin_email_whitelist(client, db_session, monkeypatch):
    import main as main_module
    monkeypatch.setattr(main_module, "ADMIN_EMAILS", ["admin@trafficvision.ai"])

    # Email in whitelist => admin
    resp = client.post("/auth/signup", json={
        "email": "admin@trafficvision.ai",
        "name": "Admin User",
        "password": "securepassword123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["role"] == "admin"

    # Non-whitelisted email => viewer, even if first user
    resp2 = client.post("/auth/signup", json={
        "email": "nonwhitelist@trafficvision.ai",
        "name": "Regular User",
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
    viewer = User(email="viewer_challan@test.com", name="Viewer", password_hash=hash_password("p"), role="viewer")
    db_session.add_all([admin, viewer])
    db_session.commit()
    admin_token = create_access_token(admin.id, admin.email)
    viewer_token = create_access_token(viewer.id, viewer.email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

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

    resp_new = client.get(f"/alerts/{alert.id}/challan", headers=admin_headers)
    assert resp_new.status_code == 400
    assert "reviewed" in resp_new.json()["detail"]

    # 2. Non-violation types like pothole or emergency_vehicle must be refused
    pothole_alert = Alert(alert_type="pothole", message="Pothole detected", status="reviewed")
    db_session.add(pothole_alert)
    db_session.commit()
    db_session.refresh(pothole_alert)
    resp_pothole = client.get(f"/alerts/{pothole_alert.id}/challan", headers=admin_headers)
    assert resp_pothole.status_code == 400
    assert "non-violation" in resp_pothole.json()["detail"]

    # 3. Add plate in PlateRead table
    plate_read = PlateRead(camera_id="camera_1", track_id=101, plate_text="DL01AB1234")
    db_session.add(plate_read)

    # 4. Viewer cannot resolve (only admin/reviewer)
    resp_viewer_resolve = client.post(
        f"/alerts/{alert.id}/resolve",
        json={"status": "reviewed", "resolution_notes": "Viewer should be rejected"},
        headers=viewer_headers,
    )
    assert resp_viewer_resolve.status_code == 403

    # 5. Invalid status rejected with 422
    resp_bad_status = client.post(
        f"/alerts/{alert.id}/resolve",
        json={"status": "challan_issued"},  # not allowed via /resolve
        headers=admin_headers,
    )
    assert resp_bad_status.status_code == 422

    # 6. Human-in-the-loop review (admin CAN resolve)
    resp_resolve = client.post(
        f"/alerts/{alert.id}/resolve",
        json={"status": "reviewed", "resolution_notes": "Confirmed by officer #42"},
        headers=admin_headers,
    )
    assert resp_resolve.status_code == 200
    assert resp_resolve.json()["status"] == "reviewed"

    # 7. GET /challan is READ-ONLY (status should NOT change to challan_issued)
    resp_challan = client.get(f"/alerts/{alert.id}/challan", headers=admin_headers)
    assert resp_challan.status_code == 200
    assert resp_challan.headers["content-type"] == "application/pdf"
    assert resp_challan.content.startswith(b"%PDF")

    db_session.refresh(alert)
    assert alert.status == "reviewed"  # unchanged - GET is read-only

    # 8. POST /issue advances to challan_issued
    resp_issue = client.post(f"/alerts/{alert.id}/challan/issue", headers=admin_headers)
    assert resp_issue.status_code == 200
    assert resp_issue.json()["status"] == "challan_issued"
    db_session.refresh(alert)
    assert alert.status == "challan_issued"

    # 9. Cannot re-issue once already challan_issued
    resp_issue2 = client.post(f"/alerts/{alert.id}/challan/issue", headers=admin_headers)
    assert resp_issue2.status_code == 422


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


# ============================================================================
# 8. FullFrameBox Crop & Downscale Rescaling Test
# ============================================================================

def test_full_frame_crop_and_rescale(tmp_path, monkeypatch):
    import numpy as np
    import cv2
    from detection.pipeline import FullFrameBox, _resize_for_detection
    from alerts import _save_evidence_crop
    import alerts

    monkeypatch.setattr(alerts, "VIOLATIONS_DIR", str(tmp_path))

    # 1. Build a 1280x720 frame with a distinctive colored rectangle at a known position
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    distinctive_color = (12, 34, 56)
    x1_full, y1_full, x2_full, y2_full = 800, 400, 1000, 600
    frame[y1_full:y2_full, x1_full:x2_full] = distinctive_color

    # 2. Simulate 640px downscale
    resized, scale = _resize_for_detection(frame)
    assert scale == 0.5
    assert resized.shape[1] == 640

    # Downscaled coordinates
    x1_down, y1_down, x2_down, y2_down = int(x1_full * scale), int(y1_full * scale), int(x2_full * scale), int(y2_full * scale)

    # Using raw downscaled box on full frame yields wrong, blank area
    bad_crop = frame[y1_down:y2_down, x1_down:x2_down]
    assert np.all(bad_crop == 0)

    # 3. Using FullFrameBox rescaled to full frame
    ff_box = FullFrameBox(int(x1_down / scale), int(y1_down / scale), int(x2_down / scale), int(y2_down / scale))
    assert ff_box.xyxy == [(x1_full, y1_full, x2_full, y2_full)]

    # 4. Assert crop used by plate/helmet/evidence path contains that rectangle
    x1, y1, x2, y2 = ff_box.xyxy[0]
    crop = frame[y1:y2, x1:x2]
    assert np.all(crop == distinctive_color)

    evidence_file = _save_evidence_crop(frame, ff_box)
    assert evidence_file is not None
    saved_crop = cv2.imread(evidence_file)
    assert saved_crop is not None
    assert saved_crop.shape == (200, 200, 3)
    assert np.all(np.abs(saved_crop.astype(int) - np.array(distinctive_color)) <= 3)


# ============================================================================
# 9. Worker Thread Alert Handling & Main Loop Broadcast Test
# ============================================================================

def test_save_and_push_alert_worker_thread(db_session):
    import threading
    import asyncio
    import alerts

    dispatched = []

    class DummyLoop:
        def is_running(self):
            return True

        def run_in_executor(self, executor, func):
            func()

    dummy_loop = DummyLoop()
    alerts.set_main_loop(dummy_loop)

    def dummy_run_coroutine_threadsafe(coro, loop):
        dispatched.append((coro, loop))
        coro.close()

    orig_run_coroutine = asyncio.run_coroutine_threadsafe
    asyncio.run_coroutine_threadsafe = dummy_run_coroutine_threadsafe
    try:
        def worker():
            alerts.save_and_push_alert("overspeed", "camera_thread_test", 9999, "Overspeed in thread", speed_kmh=110.0)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert len(dispatched) == 1
        assert dispatched[0][1] is dummy_loop
    finally:
        asyncio.run_coroutine_threadsafe = orig_run_coroutine
        alerts.set_main_loop(None)


# ============================================================================
# 10. Helmet Confirmation Flow & Bounded Attempts (Mocked API)
# ============================================================================

@pytest.mark.asyncio
async def test_helmet_consecutive_confirmation_flow(monkeypatch):
    import numpy as np
    from detection import helmet

    # Clear state
    helmet.helmet_checked_track_ids.clear()
    helmet._helmet_consecutive.clear()
    helmet._helmet_last_check.clear()
    helmet._helmet_in_flight.clear()
    helmet._helmet_attempts.clear()

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    box = (10, 10, 50, 50)
    cam = "cam_test"

    # 1. Spaced violations: 3 consecutive "without_helmet" checks trigger alert
    track_1 = 101
    calls = []

    def mock_check_helmet_violation(crop):
        calls.append("violation")
        return "without_helmet"

    monkeypatch.setattr(helmet, "check_helmet", mock_check_helmet_violation)

    # 1st violation
    await helmet.check_helmet_and_alert(cam, track_1, frame, box)
    assert (cam, track_1) not in helmet.helmet_checked_track_ids
    assert helmet._helmet_consecutive[(cam, track_1)] == 1

    # Calling immediately before CONFIRM_INTERVAL_SEC should be rate-limited
    await helmet.check_helmet_and_alert(cam, track_1, frame, box)
    assert len(calls) == 1  # no new API call

    # Advance last check time
    helmet._helmet_last_check[(cam, track_1)] -= 2.0
    await helmet.check_helmet_and_alert(cam, track_1, frame, box)
    assert (cam, track_1) not in helmet.helmet_checked_track_ids
    assert helmet._helmet_consecutive[(cam, track_1)] == 2

    # 3rd spaced violation triggers confirmation
    helmet._helmet_last_check[(cam, track_1)] -= 2.0
    await helmet.check_helmet_and_alert(cam, track_1, frame, box)
    assert (cam, track_1) in helmet.helmet_checked_track_ids
    assert len(calls) == 3

    # 2. Reset on OK: 2 violations then 'with_helmet' -> no alert and resets counter
    track_2 = 102
    helmet._helmet_last_check[(cam, track_2)] = 0.0
    await helmet.check_helmet_and_alert(cam, track_2, frame, box)
    assert helmet._helmet_consecutive[(cam, track_2)] == 1

    helmet._helmet_last_check[(cam, track_2)] -= 2.0
    await helmet.check_helmet_and_alert(cam, track_2, frame, box)
    assert helmet._helmet_consecutive[(cam, track_2)] == 2

    # Now rider has helmet
    monkeypatch.setattr(helmet, "check_helmet", lambda crop: "with_helmet")
    helmet._helmet_last_check[(cam, track_2)] -= 2.0
    await helmet.check_helmet_and_alert(cam, track_2, frame, box)
    assert helmet._helmet_consecutive[(cam, track_2)] == 0
    assert (cam, track_2) in helmet.helmet_checked_track_ids

    # 3. None results: do not count as violation, do not reset counter, retry allowed
    track_3 = 103
    monkeypatch.setattr(helmet, "check_helmet", lambda crop: None)
    helmet._helmet_last_check[(cam, track_3)] = 0.0
    await helmet.check_helmet_and_alert(cam, track_3, frame, box)
    assert helmet._helmet_consecutive[(cam, track_3)] == 0
    assert (cam, track_3) not in helmet.helmet_checked_track_ids
    assert helmet._helmet_attempts[(cam, track_3)] == 1

    # 4. Attempts capped at MAX_API_ATTEMPTS
    track_4 = 104
    api_calls_count = 0

    def counting_api(crop):
        nonlocal api_calls_count
        api_calls_count += 1
        return None

    monkeypatch.setattr(helmet, "check_helmet", counting_api)
    for _ in range(helmet.MAX_API_ATTEMPTS + 3):
        helmet._helmet_last_check[(cam, track_4)] = 0.0
        await helmet.check_helmet_and_alert(cam, track_4, frame, box)

    assert api_calls_count == helmet.MAX_API_ATTEMPTS
    assert helmet._helmet_attempts[(cam, track_4)] == helmet.MAX_API_ATTEMPTS


# ============================================================================
# 11. Speed Estimation: File vs Live Stream Timestamp Modes
# ============================================================================

def test_speed_file_vs_live_modes():
    # PIXELS_PER_METER = 8.0
    # 80 pixels = 10.0 meters over 1.0 second elapsed => 36.0 km/h
    # Mode 1: Live stream with monotonic timestamps
    live_history = deque([
        (100.0, 50, 100),
        (100.5, 90, 100),
        (101.0, 130, 100),
    ])
    speed_live = calculate_speed_kmh(live_history)
    assert speed_live == 36.0

    # Mode 2: Video file with frame_count / fps timestamps
    fps = 30.0
    file_history = deque([
        (0.0 / fps, 50, 100),
        (15.0 / fps, 90, 100),
        (30.0 / fps, 130, 100),
    ])
    speed_file = calculate_speed_kmh(file_history, fps=fps)
    assert speed_file == 36.0


# ============================================================================
# 12. Data Retention Cutoff on In-Memory SQLite
# ============================================================================

def test_data_retention_cutoff_sqlite(db_session, tmp_path, monkeypatch):
    from datetime import timedelta
    from detection.full_log import cleanup_old_face_data
    from database import DetectionLog, Alert
    import detection.full_log as full_log_module

    # Create dummy violation files
    violations_dir = tmp_path / "violations"
    violations_dir.mkdir()
    faces_dir = tmp_path / "captured_faces"
    faces_dir.mkdir()

    monkeypatch.setattr(full_log_module, "FACE_IMAGE_DIR", str(faces_dir))

    old_face_file = faces_dir / "old_face.jpg"
    old_face_file.write_text("face")

    old_violation_file = violations_dir / "old_viol.jpg"
    old_violation_file.write_text("violation")

    challan_violation_file = violations_dir / "challan_viol.jpg"
    challan_violation_file.write_text("challan")

    fresh_violation_file = violations_dir / "fresh_viol.jpg"
    fresh_violation_file.write_text("fresh")

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. DetectionLog older than 7 days
    old_log = DetectionLog(
        camera_id="cam_1",
        track_id=1,
        face_image_path=str(old_face_file),
        timestamp=now_naive - timedelta(days=10),
    )
    # 2. Alert (non-challan) older than 30 days
    old_alert = Alert(
        alert_type="overspeed",
        message="Overspeed 95 km/h",
        camera_id="cam_1",
        status="reviewed",
        evidence_path=str(old_violation_file),
        timestamp=now_naive - timedelta(days=35),
    )
    # 3. Challan issued alert: 60 days old (should NOT be deleted before 180 days)
    challan_alert = Alert(
        alert_type="overspeed",
        message="Overspeed 110 km/h",
        camera_id="cam_1",
        status="challan_issued",
        evidence_path=str(challan_violation_file),
        timestamp=now_naive - timedelta(days=60),
    )
    # 4. Fresh alert: 2 days old
    fresh_alert = Alert(
        alert_type="overspeed",
        message="Overspeed 85 km/h",
        camera_id="cam_1",
        status="new",
        evidence_path=str(fresh_violation_file),
        timestamp=now_naive - timedelta(days=2),
    )

    db_session.add_all([old_log, old_alert, challan_alert, fresh_alert])
    db_session.commit()

    old_log_id = old_log.id
    cleanup_old_face_data()

    # Re-query
    db_session.expire_all()
    assert db_session.query(DetectionLog).filter(DetectionLog.id == old_log_id).first() is None
    assert not old_face_file.exists()

    db_session.refresh(old_alert)
    assert old_alert.evidence_path is None
    assert not old_violation_file.exists()

    db_session.refresh(challan_alert)
    assert challan_alert.evidence_path == str(challan_violation_file)
    assert challan_violation_file.exists()

    db_session.refresh(fresh_alert)
    assert fresh_alert.evidence_path == str(fresh_violation_file)
    assert fresh_violation_file.exists()



