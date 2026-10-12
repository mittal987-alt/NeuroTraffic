"""
TrafficVision AI - FastAPI Backend (entry point)
------------------------------------------------
Thin entry point: wires up FastAPI routes and delegates logic to
dedicated modules. See config.py, database.py, websocket_manager.py,
alerts.py, analytics.py, detection/*.py, push_notifications.py.

Run:
    uvicorn main:app --reload

Docs: http://127.0.0.1:8000/docs
"""

import asyncio


import io
import csv
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import (
    init_db, get_db_session, VehicleEvent, Alert, PlateRead, Camera,
    DetectionLog, PotholeReport, seed_cameras,
)
from websocket_manager import connected_clients, latest_frame_jpeg
from detection.pipeline import run_all_camera_pipelines, latest_density_by_camera
from analytics import get_hourly_traffic, get_alert_breakdown, get_vehicle_type_breakdown
from pydantic import BaseModel, EmailStr
from database import User
from auth import hash_password, verify_password, create_access_token, get_current_user
from challan_generator import generate_challan_pdf
from signal_state import trigger_green_corridor, get_signal_info

class SignupRequest(BaseModel):
    email: EmailStr
    name: str
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
 
app = FastAPI(title="TrafficVision AI Backend")

# Enable CORS so the Flutter app can connect from any device/browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    init_db()
    seed_cameras()
    print("Database tables ready.")
    asyncio.create_task(run_all_camera_pipelines())


@app.get("/")
def health_check():
    return {"status": "ok", "service": "TrafficVision AI Backend"}



@app.post("/auth/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db_session)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
 
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
 
    try:
        password_hash = hash_password(payload.password)
    except RuntimeError as e:
        # This turns a silent 500 / crashed worker into a real error message
        # you'll actually see in the terminal and in the API response.
        print(f"[signup] Password hashing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
 
    user = User(email=payload.email, name=payload.name, password_hash=password_hash)
    db.add(user)
 
    try:
        db.commit()
    except IntegrityError:
        # Race condition: two signups with the same email at once, or
        # a unique constraint violation the initial check didn't catch.
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        db.rollback()
        print(f"[signup] Database commit failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not create account: {e}")
 
    db.refresh(user)
 
    token = create_access_token(user.id, user.email)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "name": user.name}}
 
 
@app.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
 
    token = create_access_token(user.id, user.email)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "name": user.name}}


@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Returns the logged-in user's info -- Flutter calls this to verify a saved token is still valid."""
    return {"id": current_user.id, "email": current_user.email, "name": current_user.name}

@app.get("/events")
def get_recent_events(limit: int = 50, db: Session = Depends(get_db_session)):
    events = db.query(VehicleEvent).order_by(VehicleEvent.timestamp.desc()).limit(limit).all()
    results = []
    for e in events:
        plate_text = None
        plate = (
            db.query(PlateRead)
            .filter(PlateRead.camera_id == e.camera_id, PlateRead.track_id == e.track_id)
            .order_by(PlateRead.timestamp.desc())
            .first()
        )
        if plate:
            plate_text = plate.plate_text

        results.append({
            "id": e.id,
            "track_id": e.track_id,
            "vehicle_type": e.vehicle_type,
            "speed_kmh": e.speed_kmh,
            "camera_id": e.camera_id,
            "plate_text": plate_text,
            "timestamp": e.timestamp.isoformat()
        })
    return results


@app.get("/stats/summary")
def get_summary_stats(db: Session = Depends(get_db_session)):
    rows = db.query(VehicleEvent.vehicle_type, func.count(VehicleEvent.id)).group_by(VehicleEvent.vehicle_type).all()
    return {vehicle_type: count for vehicle_type, count in rows}


class ResolveAlertRequest(BaseModel):
    resolution_notes: str | None = None


@app.get("/alerts")
def get_alerts(limit: int = 50, status: str | None = None, db: Session = Depends(get_db_session)):
    query = db.query(Alert)
    if status is not None:
        query = query.filter(Alert.status == status)
    alerts = query.order_by(Alert.timestamp.desc()).limit(limit).all()
    results = []
    for alert in alerts:
        plate_text = None
        if alert.track_id is not None:
            plate = (
                db.query(PlateRead)
                .filter(PlateRead.camera_id == alert.camera_id, PlateRead.track_id == alert.track_id)
                .order_by(PlateRead.timestamp.desc())
                .first()
            )
            if plate is not None:
                plate_text = plate.plate_text

        results.append({
            "id": alert.id,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "track_id": alert.track_id,
            "speed_kmh": alert.speed_kmh,
            "camera_id": alert.camera_id,
            "status": alert.status,
            "resolution_notes": alert.resolution_notes,
            "resolved_by_id": alert.resolved_by_id,
            "timestamp": alert.timestamp.isoformat(),
            "plate_text": plate_text,
        })

    return results


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    payload: ResolveAlertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == "resolved":
        return {
            "id": alert.id,
            "status": alert.status,
            "resolution_notes": alert.resolution_notes,
            "resolved_by_id": alert.resolved_by_id,
        }

    alert.status = "resolved"
    alert.resolution_notes = payload.resolution_notes
    alert.resolved_by_id = current_user.id
    db.commit()
    db.refresh(alert)
    return {
        "id": alert.id,
        "status": alert.status,
        "resolution_notes": alert.resolution_notes,
        "resolved_by_id": alert.resolved_by_id,
    }


@app.get("/alerts/{alert_id}/challan")
def download_challan_pdf(alert_id: int, db: Session = Depends(get_db_session)):
    """Generates and downloads a digital PDF E-Challan for a given violation alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Violation alert not found")

    alert_dict = {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "message": alert.message,
        "track_id": alert.track_id,
        "speed_kmh": alert.speed_kmh,
        "camera_id": alert.camera_id,
        "status": alert.status,
        "plate_text": alert.plate_text,
        "timestamp": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S") if alert.timestamp else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }

    pdf_buffer = generate_challan_pdf(alert_dict)
    filename = f"echallan_notice_{alert.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


@app.get("/export/alerts.csv")
def export_alerts_csv(
    status: str = None,
    limit: int = 1000,
    db: Session = Depends(get_db_session),
):
    """Exports violation alert records to a downloadable CSV spreadsheet."""
    query = db.query(Alert)
    if status:
        query = query.filter(Alert.status == status)
    alerts = query.order_by(Alert.timestamp.desc()).limit(limit).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Alert ID", "Timestamp (UTC)", "Camera ID", "Offense / Alert Type",
        "Vehicle Plate", "Speed (km/h)", "Status", "Resolution Notes", "System Message"
    ])

    for a in alerts:
        writer.writerow([
            a.id,
            a.timestamp.isoformat() if a.timestamp else "",
            a.camera_id,
            a.alert_type,
            a.plate_text or "N/A",
            f"{a.speed_kmh:.1f}" if a.speed_kmh is not None else "",
            a.status,
            a.resolution_notes or "",
            a.message,
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=traffic_violations_export.csv"},
    )


@app.get("/export/events.csv")
def export_events_csv(
    camera_id: str = None,
    limit: int = 1000,
    db: Session = Depends(get_db_session),
):
    """Exports vehicle tracking and counting logs to a CSV spreadsheet."""
    query = db.query(VehicleEvent)
    if camera_id:
        query = query.filter(VehicleEvent.camera_id == camera_id)
    events = query.order_by(VehicleEvent.timestamp.desc()).limit(limit).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Event ID", "Timestamp (UTC)", "Camera ID", "Track ID", "Vehicle Type", "Speed (km/h)", "Plate"])

    for e in events:
        writer.writerow([
            e.id,
            e.timestamp.isoformat() if e.timestamp else "",
            e.camera_id,
            e.track_id,
            e.vehicle_type,
            f"{e.speed_kmh:.1f}" if e.speed_kmh is not None else "",
            e.plate_text or "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vehicle_events_export.csv"},
    )


@app.post("/signals/{camera_id}/green_corridor")
def activate_green_corridor(camera_id: str, duration_sec: int = 25):
    """Manually or automated preemption trigger to force traffic signal GREEN for emergency corridors."""
    result = trigger_green_corridor(camera_id, duration_sec=duration_sec)
    return result


@app.get("/signals/{camera_id}")
def get_camera_signal(camera_id: str):
    """Fetches real-time signal state and active green corridor info for a given camera."""
    return get_signal_info(camera_id)


@app.get("/plates")
def get_plates(limit: int = 50, db: Session = Depends(get_db_session)):
    plates = db.query(PlateRead).order_by(PlateRead.timestamp.desc()).limit(limit).all()
    return [
        {"id": p.id, "track_id": p.track_id, "plate_text": p.plate_text, "confidence": p.confidence,
         "camera_id": p.camera_id, "timestamp": p.timestamp.isoformat()}
        for p in plates
    ]


@app.get("/logs")
def get_detection_logs(limit: int = 50, db: Session = Depends(get_db_session)):
    """Full detection log: plate + speed + face captured on every logged occurrence."""
    logs = db.query(DetectionLog).order_by(DetectionLog.timestamp.desc()).limit(limit).all()
    return [
        {"id": l.id, "track_id": l.track_id, "camera_id": l.camera_id, "plate_text": l.plate_text,
         "speed_kmh": l.speed_kmh, "face_image_path": l.face_image_path, "timestamp": l.timestamp.isoformat()}
        for l in logs
    ]


@app.get("/cameras")
def get_cameras(db: Session = Depends(get_db_session)):
    cameras = db.query(Camera).all()
    return [
        {"id": c.id, "name": c.name, "latitude": c.latitude, "longitude": c.longitude,
         "status": c.status, "last_seen": c.last_seen.isoformat()}
        for c in cameras
    ]


@app.get("/density")
def get_current_density():
    return latest_density_by_camera


@app.get("/analytics/hourly")
def hourly_traffic(hours_back: int = 24, db: Session = Depends(get_db_session)):
    return get_hourly_traffic(db, hours_back=hours_back)


@app.get("/analytics/alerts")
def alert_breakdown(db: Session = Depends(get_db_session)):
    return get_alert_breakdown(db)


@app.get("/analytics/vehicle_types")
def vehicle_type_breakdown(db: Session = Depends(get_db_session)):
    return get_vehicle_type_breakdown(db)


async def _mjpeg_generator(camera_id: str):
    while True:
        frame_bytes = latest_frame_jpeg.get(camera_id)
        if frame_bytes:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        await asyncio.sleep(0.05)  # ~20fps cap on the preview stream


@app.get("/stream/{camera_id}")
def video_stream(camera_id: str):
    """Live MJPEG video preview for the given camera -- what the Flutter app's Live Feed screen displays."""
    return StreamingResponse(_mjpeg_generator(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")
@app.get("/potholes")
def get_potholes(limit: int = 50, db: Session = Depends(get_db_session)):
    reports = db.query(PotholeReport).order_by(PotholeReport.timestamp.desc()).limit(limit).all()
    return [
        {"id": r.id, "camera_id": r.camera_id, "confidence": r.confidence,
         "frame_x": r.frame_x, "frame_y": r.frame_y, "timestamp": r.timestamp.isoformat()}
        for r in reports
    ]

@app.websocket("/ws/live")
async def websocket_live_feed(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"Client connected. Total clients: {len(connected_clients)}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
        print(f"Client disconnected. Total clients: {len(connected_clients)}")