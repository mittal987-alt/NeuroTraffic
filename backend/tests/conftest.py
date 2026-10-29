"""
TrafficVision AI - Test Configuration and Fixtures
--------------------------------------------------
Sets up in-memory SQLite database, TestClient, and mocks heavy AI libraries.
"""

import os
import sys

# Force in-memory SQLite for all tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from unittest.mock import MagicMock

# 1. Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 2. Mock heavy imports before any module loads them
for mod in [
    "ultralytics",
    "easyocr",
    "firebase_admin",
    "firebase_admin.credentials",
    "firebase_admin.messaging",
    "inference_sdk",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import database
from database import Base, get_db_session

# Re-initialize database engine to in-memory StaticPool SQLite
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.engine = test_engine
database.SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=test_engine)

# Patch modules that import SessionLocal directly
import alerts
alerts.SessionLocal = database.SessionLocal
import detection.full_log
detection.full_log.SessionLocal = database.SessionLocal
import detection.emergency
detection.emergency.SessionLocal = database.SessionLocal
import detection.pipeline
detection.pipeline.SessionLocal = database.SessionLocal


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture
def db_session():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from main import app

    def override_get_db():
        session = database.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
