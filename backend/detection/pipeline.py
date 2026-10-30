"""
TrafficVision AI - Detection pipeline (multi-camera, multi-source)
------------------------------------------------
Runs one independent detection loop per camera in CAMERA_SOURCES.
Supports three source types:
    "file"       - local video file, loops forever when it ends
    "youtube"    - YouTube live stream, resolved via yt-dlp, reconnects on drop
    "ip_webcam"  - phone running IP Webcam app, reconnects on drop

Each loop has its own YOLO model instance (critical -- sharing one
model across sources would corrupt ByteTrack's internal track state)
and its own local counters, tagging every event/broadcast with its
camera_id so downstream consumers can tell cameras apart.

PERFORMANCE NOTES (read this if the live feed feels laggy):
  - cap.read() and model.track() are blocking/CPU-bound calls. They
    run in a background thread via asyncio.to_thread() so they don't
    freeze the whole server (WebSocket broadcasts, other endpoints,
    other cameras) while they execute.
  - Full YOLO detection only runs every DETECTION_FRAME_SKIP frames
    (see config.py). Frames in between are still streamed live (so
    the video looks smooth) but skip the expensive inference step,
    reusing the last known boxes for the live overlay.
  - Lane + pothole checks are whole-frame, extra-expensive checks
    (each is a network call to Roboflow). They run on their own,
    longer interval (WHOLE_FRAME_CHECK_INTERVAL) instead of every
    processed frame.
"""

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone
import time
import numpy as np

import cv2
from ultralytics import YOLO

from config import (
    CAMERA_SOURCES, VEHICLE_CLASSES, CONF_THRESHOLD, HISTORY_LENGTH, LINE_Y,
    DETECTION_FRAME_SKIP, WHOLE_FRAME_CHECK_INTERVAL, JPEG_QUALITY, DETECTION_RESIZE_WIDTH,
)
from database import VehicleEvent, Camera, SessionLocal
from websocket_manager import broadcast, latest_frame_jpeg
from detection.speed import calculate_speed_kmh, check_overspeed
from detection.wrong_way import check_wrong_way
from detection.helmet import check_helmet_and_alert
from detection.plate import check_plate_and_save, latest_detected_plates, cleanup_old_plates
from detection.pothole import check_potholes
from detection.seatbelt import check_seatbelt_and_alert
from detection.redlight import check_red_light_violation
from detection.density import calculate_density
from detection.full_log import log_full_detection
from detection.lane import get_current_lane_polygons, check_lane_departure
from detection.accident import record_speed, check_accident, cleanup_old_tracks
from detection.emergency import check_emergency_vehicle
from signal_state import get_signal_state, is_green_corridor_active
from alerts import set_main_loop

try:
    from youtube_stream import get_direct_stream_url
except ImportError:
    get_direct_stream_url = None  # only needed if a "youtube" source is configured

# In-memory snapshot of the latest density reading per camera, so the
# /density REST endpoint can return something without waiting for a
# WebSocket message.
latest_density_by_camera: dict[str, dict] = {}

background_tasks = set()

class FullFrameBox:
    """Represents a bounding box in full-frame pixel coordinates."""
    def __init__(self, x1: int, y1: int, x2: int, y2: int):
        self.x1 = int(x1)
        self.y1 = int(y1)
        self.x2 = int(x2)
        self.y2 = int(y2)
        self.xyxy = [(self.x1, self.y1, self.x2, self.y2)]

    def __iter__(self):
        return iter((self.x1, self.y1, self.x2, self.y2))

    def __getitem__(self, item):
        return (self.x1, self.y1, self.x2, self.y2)[item]

    def __repr__(self):
        return f"FullFrameBox({self.x1}, {self.y1}, {self.x2}, {self.y2})"


def fire_and_forget(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    
    def handle_exception(t):
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Background task failed: {e}")
            import traceback
            traceback.print_exc()
            
    task.add_done_callback(handle_exception)
    return task


def save_crossing_event(camera_id: str, track_id: int, vehicle_type: str, speed_kmh: float | None):
    """Writes one row to the database for a vehicle that just crossed the line."""
    db = SessionLocal()
    try:
        event = VehicleEvent(
            track_id=track_id,
            vehicle_type=vehicle_type,
            speed_kmh=speed_kmh,
            camera_id=camera_id,
        )
        db.add(event)
        db.commit()
    finally:
        db.close()


def update_camera_heartbeat(camera_id: str):
    """Updates a camera's last_seen timestamp and status -- called
    periodically (not every frame) so the Camera Map screen reflects
    that this camera's pipeline is actually alive."""
    db = SessionLocal()
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()
        if camera:
            camera.last_seen = datetime.now(timezone.utc)
            camera.status = "online"
            db.commit()
    finally:
        db.close()


def _open_capture(source_type: str, video_path: str) -> cv2.VideoCapture:
    """
    Opens a video source based on its type. Handles local Windows paths
    and network streams.
    """
    if source_type == "youtube":
        if get_direct_stream_url is None:
            raise RuntimeError("youtube_stream module not available -- install yt-dlp")
        stream_url = get_direct_stream_url(video_path)
        cap = cv2.VideoCapture(stream_url)
    elif str(video_path).isdigit():
        cap = cv2.VideoCapture(int(video_path))
    else:
        # Handles both local files AND direct URLs (e.g. http://.../video).
        # Using normalized path for local files to avoid Windows backslash issues.
        normalized_path = video_path.replace("\\", "/")
        cap = cv2.VideoCapture(normalized_path)

    # Shrinks the internal OpenCV buffer
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _run_detection_sync(model: YOLO, frame):
    """
    The actual blocking YOLO call, run off the event loop via
    asyncio.to_thread(). Kept as a plain sync function so it can be
    handed to a worker thread cleanly.
    """
    results = model.track(
        frame,
        conf=CONF_THRESHOLD,
        classes=list(VEHICLE_CLASSES.keys()),
        persist=True,
        tracker="bytetrack.yaml",
        verbose=False,
    )
    return results[0]


def _resize_for_detection(frame):
    """Downscales the frame before running YOLO if DETECTION_RESIZE_WIDTH
    is set -- smaller input means noticeably faster inference on CPU.
    Returns (resized_frame, scale_factor) so detected box coordinates
    can be scaled back up to the original frame for drawing/streaming."""
    if not DETECTION_RESIZE_WIDTH:
        return frame, 1.0
    h, w = frame.shape[:2]
    if w <= DETECTION_RESIZE_WIDTH:
        return frame, 1.0
    scale = DETECTION_RESIZE_WIDTH / w
    resized = cv2.resize(frame, (DETECTION_RESIZE_WIDTH, int(h * scale)))
    return resized, scale


async def run_camera_pipeline(camera_id: str, source_type: str, video_path: str):
    """
    Runs detection for ONE camera. Each call gets its own YOLO model
    instance. If the primary source fails, it falls back to traffic.mp4.
    """
    set_main_loop(asyncio.get_running_loop())
    model = YOLO("yolov8n.pt")
    is_fallback = False

    try:
        cap = _open_capture(source_type, video_path)
        if not cap.isOpened():
            raise Exception("Primary source could not be opened")
    except Exception as e:
        print(f"[{camera_id}] Primary source failed ({e}). Falling back to traffic.mp4...")
        cap = cv2.VideoCapture("traffic.mp4")
        source_type = "file"
        is_fallback = True

    if not cap.isOpened():
        print(f"ERROR [{camera_id}]: Neither primary nor fallback source could be opened")
        db = SessionLocal()
        try:
            cam = db.query(Camera).filter(Camera.id == camera_id).first()
            if cam:
                cam.status = "offline"
                cam.last_seen = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()
        return

    # Check for optional camera calibration points for homography
    homography_matrix = None
    cam_cfg = next((c for c in CAMERA_SOURCES if c.get("id") == camera_id), None)
    if cam_cfg and "calibration_points" in cam_cfg:
        try:
            calib = cam_cfg["calibration_points"]
            img_pts = np.float32(calib["image_points"])
            world_pts = np.float32(calib["world_points"])
            homography_matrix = cv2.getPerspectiveTransform(img_pts, world_pts)
        except Exception as e:
            print(f"[{camera_id}] Homography calculation failed: {e}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    position_history = defaultdict(lambda: deque(maxlen=HISTORY_LENGTH))
    last_side_of_line = {}
    counted_ids = set()
    class_counts = {label: 0 for label in VEHICLE_CLASSES.values()}
    latest_speed_kmh = {}

    # Cache of the last drawn frame's detections, reused on frames we
    # skip full inference for -- keeps the live video feeling smooth
    # instead of only updating once every DETECTION_FRAME_SKIP frames.
    last_vehicles_this_frame = []
    last_lane_polygons = None

    frame_count = 0
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    print(f"Detection pipeline started for {camera_id} ({source_type}).")

    is_live_stream = source_type in ("youtube", "ip_webcam") or str(video_path).isdigit()

    while True:
        # For live streams (IP Webcam / physical camera), grab and retrieve immediately.
        # If running on CPU inference, the internal buffer accumulates old frames.
        # We grab once or twice to flush any buffered frames so the feed stays real-time.
        if is_live_stream:
            cap.grab()

        ret, frame = await asyncio.to_thread(cap.read)

        if not ret:
            if is_live_stream:
                # Live source dropped -- reconnect rather than loop.
                print(f"[{camera_id}] Stream dropped, reconnecting...")
                cap.release()
                await asyncio.sleep(2)
                try:
                    cap = _open_capture(source_type, video_path)
                except Exception as e:
                    print(f"[{camera_id}] Reconnect failed ({e}), retrying in 5s...")
                    await asyncio.sleep(5)
                continue
            else:
                # Local file -- loop indefinitely.
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

        frame_count += 1

        if frame_count % 30 == 0:
            update_camera_heartbeat(camera_id)

        run_full_detection = (frame_count % DETECTION_FRAME_SKIP == 0)
        run_whole_frame_checks = (frame_count % WHOLE_FRAME_CHECK_INTERVAL == 0)

        # --- Whole-frame checks (lane + pothole): throttled, since
        # each one is a network call to an external API and doesn't
        # need to run on every single frame to be useful. ---
        if run_whole_frame_checks:
            last_lane_polygons = await asyncio.to_thread(get_current_lane_polygons, camera_id, frame.copy())
            await asyncio.to_thread(check_potholes, camera_id, frame.copy())
        lane_polygons = last_lane_polygons

        vehicles_this_frame = last_vehicles_this_frame

        if run_full_detection:
            clean_frame = frame.copy()
            detect_frame, scale = _resize_for_detection(frame)
            # model.track() is CPU-bound -- also offloaded to a thread
            # so it doesn't block WebSocket/API handling on the server
            # while inference runs.
            result = await asyncio.to_thread(_run_detection_sync, model, detect_frame)
            vehicles_this_frame = []

            if result.boxes.id is not None:
                track_ids = result.boxes.id.int().tolist()
                for box, track_id in zip(result.boxes, track_ids):
                    class_id = int(box.cls[0])
                    label = VEHICLE_CLASSES.get(class_id, "vehicle")
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    if scale != 1.0:
                        x1, y1, x2, y2 = int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale)
                    ff_box = FullFrameBox(x1, y1, x2, y2)
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    # Bottom-center (ground contact point) for homography accuracy
                    gx, gy = cx, y2

                    # Timestamp: use real elapsed time for live streams,
                    # frame-number-derived time for files (avoids drift from processing delay).
                    if is_live_stream:
                        t_now = time.monotonic()
                    else:
                        t_now = frame_count / fps
                    position_history[track_id].append((t_now, gx, gy))

                    # --- Line-crossing count + red-light check ---
                    side = "above" if cy < LINE_Y else "below"
                    if track_id in last_side_of_line and last_side_of_line[track_id] != side:
                        if track_id not in counted_ids:
                            counted_ids.add(track_id)
                            class_counts[label] += 1
                            save_crossing_event(camera_id, track_id, label, latest_speed_kmh.get(track_id))
                            check_red_light_violation(camera_id, track_id, label, frame=clean_frame, box=ff_box)
                    last_side_of_line[track_id] = side

                    # --- Speed + overspeed alert ---
                    history = position_history[track_id]
                    speed_kmh = calculate_speed_kmh(history, fps, homography_matrix=homography_matrix)
                    if speed_kmh is not None:
                        latest_speed_kmh[track_id] = speed_kmh
                        check_overspeed(camera_id, track_id, label, speed_kmh, frame=clean_frame, box=ff_box)
                        record_speed(camera_id, track_id, speed_kmh)

                    # --- Wrong-way check ---
                    check_wrong_way(camera_id, track_id, label, history, frame=clean_frame, box=ff_box)

                    # --- Lane departure check (skipped until we have at
                    # least one cached set of lane polygons) ---
                    if lane_polygons is not None:
                        check_lane_departure(camera_id, track_id, label, cx, cy, lane_polygons, frame=clean_frame, box=ff_box)

                    # --- Type-specific checks (backgrounded, non-blocking) ---
                    if label == "motorcycle":
                        fire_and_forget(check_helmet_and_alert(camera_id, track_id, clean_frame, ff_box))
                        fire_and_forget(check_plate_and_save(camera_id, track_id, clean_frame, ff_box))
                    elif label in ("car", "truck", "bus"):
                        fire_and_forget(check_plate_and_save(camera_id, track_id, clean_frame, ff_box))
                        fire_and_forget(check_seatbelt_and_alert(camera_id, track_id, label, clean_frame, ff_box))

                    # --- Full log: plate + speed + face, every occurrence (throttled) ---
                    fire_and_forget(
                        log_full_detection(camera_id, track_id, frame_count, clean_frame, ff_box, latest_speed_kmh.get(track_id))
                    )

                    vehicles_this_frame.append(
                        {
                            "id": track_id,
                            "track_id": track_id,
                            "type": label,
                            "vehicle_type": label,
                            "speed_kmh": latest_speed_kmh.get(track_id),
                            "box": (x1, y1, x2, y2),
                            "plate_text": latest_detected_plates.get((camera_id, track_id)),
                        }
                    )

            last_vehicles_this_frame = vehicles_this_frame

            # --- Accident check: needs ALL vehicles in the frame together ---
            check_accident(camera_id, vehicles_this_frame)

            # --- Emergency vehicle & Green Corridor check ---
            for v in vehicles_this_frame:
                check_emergency_vehicle(
                    camera_id=camera_id,
                    track_id=v["track_id"],
                    vehicle_type=v["type"],
                    plate_text=v.get("plate_text"),
                )

            # Periodically clean up memory for vehicles that have left the scene
            if frame_count % 300 == 0:
                active_ids = {v["track_id"] for v in vehicles_this_frame}
                cleanup_old_tracks(active_ids, camera_id)
                cleanup_old_plates(active_ids, camera_id)

        # --- Draw boxes for whichever vehicles we currently know about
        # (freshly detected this frame, or carried over from the last
        # detection pass) -- every frame gets boxes drawn so the video
        # doesn't visually "blink" between detected/undetected frames. ---
        for v in vehicles_this_frame:
            x1, y1, x2, y2 = v["box"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Show ID, type, and PLATE if available
            label_text = f"ID{v['track_id']} {v['type']}"
            if v.get("plate_text"):
                label_text += f" [{v['plate_text']}]"

            cv2.putText(frame, label_text, (x1, max(y1 - 8, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # --- Visual indicator for Emergency Green Corridor ---
        green_corridor_active = is_green_corridor_active(camera_id)
        if green_corridor_active:
            # Draw prominent top alert banner
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 200), -1)
            cv2.putText(
                frame,
                "*** EMERGENCY GREEN CORRIDOR ACTIVE ***",
                (int(w * 0.15), 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
            )

        # --- Traffic density ---
        density_info = calculate_density(len(vehicles_this_frame))
        latest_density_by_camera[camera_id] = density_info

        # --- Encode frame for MJPEG live preview (lower quality = faster
        # encode + smaller payload over the hotspot connection) ---
        success, jpeg_bytes = cv2.imencode(".jpg", frame, encode_params)
        if success:
            latest_frame_jpeg[camera_id] = jpeg_bytes.tobytes()

        # --- Broadcast this frame's full state to connected WebSocket clients ---
        vehicles_for_broadcast = [
            {"id": v["id"], "type": v["type"], "speed_kmh": v["speed_kmh"], "plate_text": v.get("plate_text")}
            for v in vehicles_this_frame
        ]

        await broadcast(
            {
                "camera_id": camera_id,
                "frame": frame_count,
                "vehicles": vehicles_for_broadcast,
                "counts": class_counts,
                "density": density_info,
                "signal_state": get_signal_state(camera_id),
                "is_green_corridor": green_corridor_active,
            }
        )

        # For pre-recorded files, sleep to match 30 FPS. For live streams,
        # don't artificial-sleep, yield immediately so frames don't lag behind.
        if not is_live_stream:
            await asyncio.sleep(1 / fps)
        else:
            await asyncio.sleep(0.001)


async def run_all_camera_pipelines():
    """Launches one independent pipeline task per configured camera."""
    tasks = [
        run_camera_pipeline(source["id"], source["source_type"], source["video_path"])
        for source in CAMERA_SOURCES
    ]
    await asyncio.gather(*tasks)