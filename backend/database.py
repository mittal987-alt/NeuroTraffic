"""
TrafficVision AI - Database layer
------------------------------------------------
Defines the PostgreSQL (Neon) connection and all tables:
  - vehicle_events: one row per vehicle that crossed the counting line
  - alerts: one row per alert-worthy event (overspeed, wrong-way, etc.)
  - plate_reads: one row per successfully OCR'd license plate
  - cameras: one row per configured camera (location, status)
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

def now_utc():
    return datetime.now(timezone.utc)

# Neon (managed Postgres) pooled connection string or local SQLite fallback
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./traffic.db")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./traffic.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class PotholeReport(Base):
    """One row per detected pothole location -- reported once per
    physical location (deduped by rounded coordinates), not once per
    frame it remains visible."""

    __tablename__ = "pothole_reports"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, default="camera_1")
    confidence = Column(Float, nullable=True)
    frame_x = Column(Float, nullable=True)  # approximate location in-frame
    frame_y = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=now_utc)


class User(Base):
    """Registered app users. Passwords are stored as bcrypt hashes,
    never in plaintext."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=now_utc)


class DetectionLog(Base):
    """One row per full detection occurrence -- plate, speed, and face
    crop path together, logged EVERY time (not deduped per vehicle).
    This is the audit trail; PlateRead/Alert remain the summary tables."""

    __tablename__ = "detection_logs"

    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, nullable=True)
    camera_id = Column(String, default="camera_1")
    plate_text = Column(String, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    face_image_path = Column(String, nullable=True)
    timestamp = Column(DateTime, default=now_utc)


class VehicleEvent(Base):
    """One row per vehicle that crossed the counting line."""

    __tablename__ = "vehicle_events"

    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, nullable=False)
    vehicle_type = Column(String, nullable=False)
    speed_kmh = Column(Float, nullable=True)
    camera_id = Column(String, default="camera_1")
    timestamp = Column(DateTime, default=now_utc)


class Alert(Base):
    """One row per alert-worthy event (overspeed, wrong-way, no-helmet,
    no-seatbelt, red-light). Separate from VehicleEvent because not
    every detection is alert-worthy -- alerts are the subset that
    should trigger a push notification."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    track_id = Column(Integer, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    camera_id = Column(String, default="camera_1")
    status = Column(String, default="new")
    resolved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(String, nullable=True)
    evidence_path = Column(String, nullable=True)
    timestamp = Column(DateTime, default=now_utc)


class PlateRead(Base):
    """One row per license plate successfully read via OCR. This is
    data capture, not an alert -- no push notification, just storage."""

    __tablename__ = "plate_reads"

    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, nullable=True)
    plate_text = Column(String, nullable=False)
    confidence = Column(Float, nullable=True)
    camera_id = Column(String, default="camera_1")
    timestamp = Column(DateTime, default=now_utc)


class Camera(Base):
    """Represents a physical camera. Supports multiple cameras --
    each row is one entry from config.py's CAMERA_SOURCES."""

    __tablename__ = "cameras"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    status = Column(String, default="online")
    last_seen = Column(DateTime, default=now_utc)


def init_db():
    """Creates all tables if they don't exist yet, with safe migration for evidence_path."""
    Base.metadata.create_all(bind=engine)

    # Safe migration for existing SQLite DBs when evidence_path is missing
    with engine.connect() as conn:
        try:
            if DATABASE_URL.startswith("sqlite"):
                res = conn.execute(text("PRAGMA table_info(alerts)"))
                col_names = [row[1] for row in res.fetchall()]
                if "evidence_path" not in col_names:
                    conn.execute(text("ALTER TABLE alerts ADD COLUMN evidence_path VARCHAR"))
                    conn.commit()
            else:
                conn.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS evidence_path VARCHAR"))
                conn.commit()
        except Exception as e:
            print(f"Migration note: {e}")


def seed_cameras():
    """Ensures a database row exists for every camera in CAMERA_SOURCES."""
    from config import CAMERA_SOURCES

    db = SessionLocal()
    try:
        offsets = [(0, 0), (0.002, 0.002), (-0.002, -0.002)]
        for i, source in enumerate(CAMERA_SOURCES):
            existing = db.query(Camera).filter(Camera.id == source["id"]).first()
            if not existing:
                off_lat, off_lng = offsets[i % len(offsets)]
                camera = Camera(
                    id=source["id"],
                    name=source["name"],
                    latitude=28.6139 + off_lat,
                    longitude=77.2090 + off_lng,
                    status="online",
                    last_seen=now_utc(),
                )
                db.add(camera)
        db.commit()
    finally:
        db.close()


def get_db_session():
    """Yields a database session; use as a FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()