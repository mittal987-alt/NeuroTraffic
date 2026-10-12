"""
TrafficVision AI - Configuration
------------------------------------------------
All tunable constants live here. This is the file you edit when
setting up a new camera/video, adjusting thresholds, or adding
credentials -- no need to hunt through logic files for a number to
tweak.

Values are read from the .env file (via python-dotenv) with sensible
defaults so the app still runs if an env var is missing.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Each entry is one "camera" -- it now pulls paths from your .env file
CAMERA_SOURCES = [
    {
        "id": "camera_1",
        "source_type": "file" if os.getenv("CAMERA_1_VIDEO_PATH", "").lower().endswith(".mp4") else "ip_webcam",
        "video_path": os.getenv("CAMERA_1_VIDEO_PATH", "traffic.mp4"),
        "name": "Primary Camera",
    },
]

# JWT Secret Key from .env
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "insecure-dev-key-change-me")


# --- Vehicle classes (COCO class IDs -> readable labels) ---
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

# --- Detection tuning ---
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.4"))
HISTORY_LENGTH = 10  # how many past positions to keep per vehicle

# --- Performance tuning (added to fix live feed lag on CPU) ---
# Run full YOLO detection every Nth frame. Frames in between still
# stream live (using the last known boxes) but skip the expensive
# inference step. Raise this (e.g. to 3-4) if it's still laggy;
# lower it (e.g. to 1) if detection feels too infrequent/jumpy.
DETECTION_FRAME_SKIP = int(os.getenv("DETECTION_FRAME_SKIP", "4"))

# Lane + pothole checks each make a network call to Roboflow -- don't
# run them every processed frame. This runs them roughly once per
# second on a 30fps source.
WHOLE_FRAME_CHECK_INTERVAL = int(os.getenv("WHOLE_FRAME_CHECK_INTERVAL", "30"))

# JPEG quality (1-100) for the MJPEG live preview stream. Lower =
# faster encode + smaller payload over the network = less lag, at
# the cost of visual quality. 100 is near-lossless; 50-60 is a good
# starting point for a laggy phone-hotspot connection.
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "60"))

# Downscale frames to this width (px) before running YOLO -- smaller
# input = faster inference on CPU. Set to None to disable and run
# detection at full camera resolution. Detected boxes are scaled back
# up automatically so they still align correctly with the streamed
# (full-resolution) video.
DETECTION_RESIZE_WIDTH = int(os.getenv("DETECTION_RESIZE_WIDTH", "640"))

# --- Counting line ---
LINE_Y = int(os.getenv("LINE_Y", "240"))  # y-coordinate of the counting line, in pixels

# --- Speed estimation ---
PIXELS_PER_METER = float(os.getenv("PIXELS_PER_METER", "8.0"))  # calibrate this for your camera
SPEED_LIMIT_KMH = float(os.getenv("SPEED_LIMIT_KMH", "80.0"))

# --- Wrong-way detection ---
# (dx, dy) describing NORMAL traffic direction. y increases DOWNWARD
# on screen. (0, 1) = normal traffic flows top-to-bottom.
EXPECTED_DIRECTION = (0, 1)
WRONG_WAY_MIN_DISPLACEMENT_PX = 40

# --- Firebase push notifications ---
# Paste the FCM token printed in the Flutter app's console on startup.
# Later phase: store per-device tokens in the database instead.
TEST_DEVICE_TOKEN = os.getenv("FCM_DEVICE_TOKEN", "PASTE_YOUR_FCM_TOKEN_HERE")