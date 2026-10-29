"""
TrafficVision AI - Phase 3: Counting + Speed Estimation
------------------------------------------------------------
Builds on Phase 2's tracking. Adds:
  1. Line-crossing counter: a virtual line across the road; each
     tracked vehicle is counted once when its center crosses it.
  2. Speed estimation: uses each vehicle's position history + a
     pixels-per-meter calibration to estimate km/h.

SPEED CALIBRATION (important, read this):
    Speed is calculated in pixels-per-frame, then converted to real
    units using --pixels-per-meter. This value depends entirely on
    your camera's distance/angle to the road, so a value that's
    "correct" for one video will be wrong for another.

    To calibrate: pick two points in your video that are a known
    real-world distance apart (e.g. lane markings are usually ~3m
    apart, or measure two points on the road yourself), measure the
    pixel distance between them (e.g. using any image tool), then:

        pixels_per_meter = pixel_distance / real_distance_in_meters

    Until you calibrate properly, treat the speed numbers as
    RELATIVE (useful for comparing "fast" vs "slow" vehicles) rather
    than accurate km/h.

Run:
    python count_and_speed.py --video traffic.mp4 \
        --line-y 400 --pixels-per-meter 8
"""

import argparse
from collections import defaultdict, deque

import cv2
from ultralytics import YOLO

VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# How many past positions to keep per vehicle (for speed smoothing)
HISTORY_LENGTH = 10


def main(video_path, model_name, conf_threshold, line_y, pixels_per_meter, show_window):
    model = YOLO(model_name)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30  # fall back to 30 if unavailable

    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video resolution: {video_width}x{video_height}, fps={fps:.1f}")
    if not (0 < line_y < video_height):
        print(
            f"WARNING: --line-y {line_y} is outside the frame height (0-{video_height}). "
            f"The line will never be crossed. Try something like --line-y {video_height // 2}."
        )

    # Per-track-ID state
    position_history = defaultdict(lambda: deque(maxlen=HISTORY_LENGTH))
    last_side_of_line = {}  # track_id -> "above" or "below"
    counted_ids = set()
    class_counts = {label: 0 for label in VEHICLE_CLASSES.values()}
    latest_speed_kmh = {}  # track_id -> most recent speed estimate

    frame_count = 0
    frame_width = None
    min_cy_seen = None
    max_cy_seen = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        if frame_width is None:
            frame_width = frame.shape[1]

        results = model.track(
            frame,
            conf=conf_threshold,
            classes=list(VEHICLE_CLASSES.keys()),
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        result = results[0]

        # Draw the counting line
        cv2.line(frame, (0, line_y), (frame_width, line_y), (255, 0, 0), 2)

        if result.boxes.id is not None:
            track_ids = result.boxes.id.int().tolist()
            for box, track_id in zip(result.boxes, track_ids):
                class_id = int(box.cls[0])
                label = VEHICLE_CLASSES.get(class_id, "vehicle")

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2  # center point

                position_history[track_id].append((frame_count, cx, cy))

                min_cy_seen = cy if min_cy_seen is None else min(min_cy_seen, cy)
                max_cy_seen = cy if max_cy_seen is None else max(max_cy_seen, cy)

                # --- Line crossing check ---
                side = "above" if cy < line_y else "below"
                if track_id in last_side_of_line and last_side_of_line[track_id] != side:
                    # Vehicle crossed the line since last frame
                    if track_id not in counted_ids:
                        counted_ids.add(track_id)
                        class_counts[label] += 1
                last_side_of_line[track_id] = side

                # --- Speed estimation ---
                history = position_history[track_id]
                if len(history) >= 2:
                    f0, x0, y0 = history[0]
                    f1, x1_, y1_ = history[-1]
                    frame_gap = f1 - f0
                    if frame_gap > 0:
                        pixel_dist = ((x1_ - x0) ** 2 + (y1_ - y0) ** 2) ** 0.5
                        seconds_elapsed = frame_gap / fps
                        meters = pixel_dist / pixels_per_meter
                        speed_kmh = (meters / seconds_elapsed) * 3.6
                        latest_speed_kmh[track_id] = speed_kmh

                # --- Draw box + info ---
                speed_text = f" {latest_speed_kmh[track_id]:.0f}km/h" if track_id in latest_speed_kmh else ""
                color = (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    frame,
                    f"ID{track_id} {label}{speed_text}",
                    (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2,
                )

        # HUD: running counts
        y_offset = 30
        for label, count in class_counts.items():
            cv2.putText(frame, f"{label}: {count}", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            y_offset += 25

        if show_window:
            cv2.imshow("TrafficVision AI - Phase 3 (Counting + Speed)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if show_window:
        cv2.destroyAllWindows()

    if min_cy_seen is not None:
        print(f"\nVehicles were detected between y={min_cy_seen} and y={max_cy_seen} in this video.")
        print(f"Your --line-y was {line_y}. For crossings to register, pick a value inside that range.")

    print("\n--- Final counts (vehicles that crossed the line) ---")
    for label, count in class_counts.items():
        print(f"{label}: {count}")

    if latest_speed_kmh:
        avg_speed = sum(latest_speed_kmh.values()) / len(latest_speed_kmh)
        print(f"\nAverage of last-known speeds: {avg_speed:.1f} km/h")
        print("(Remember: accurate only if --pixels-per-meter was calibrated for this camera.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3 counting + speed estimation")
    parser.add_argument("--video", type=str, default="traffic.mp4")
    parser.add_argument("--model", type=str, default="yolov8n.pt")
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--line-y", type=int, default=400, help="Y-coordinate (pixels) of the counting line")
    parser.add_argument(
        "--pixels-per-meter",
        type=float,
        default=8.0,
        help="Calibration value: how many pixels correspond to 1 real-world meter (see docstring)",
    )
    parser.add_argument("--no-window", action="store_true")
    args = parser.parse_args()

    main(args.video, args.model, args.conf, args.line_y, args.pixels_per_meter, show_window=not args.no_window)