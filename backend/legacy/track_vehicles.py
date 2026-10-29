"""
TrafficVision AI - Phase 2: Vehicle Tracking
------------------------------------------------
Same as Phase 1, but now each vehicle gets a persistent ID as it
moves across frames. This is the building block for:
  - accurate counting (count unique IDs, not detections)
  - speed estimation (track an ID's position over time)
  - wrong-way detection (track an ID's direction over time)

Run:
    python track_vehicles.py --video traffic.mp4

Press 'q' to quit the preview window early.
"""

import argparse

import cv2
from ultralytics import YOLO

VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


def main(video_path: str, model_name: str, conf_threshold: float, show_window: bool):
    model = YOLO(model_name)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")

    # unique_ids_seen: every track ID we've ever seen, grouped by vehicle type.
    # This is the "real" count -- each vehicle counted exactly once, no matter
    # how many frames it appears in.
    unique_ids_seen = {label: set() for label in VEHICLE_CLASSES.values()}

    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        # model.track() instead of model() -- this is the whole change from Phase 1.
        # persist=True tells YOLO to remember tracks between calls (i.e. across frames).
        # tracker="bytetrack.yaml" selects ByteTrack (a built-in tracker config).
        results = model.track(
            frame,
            conf=conf_threshold,
            classes=list(VEHICLE_CLASSES.keys()),
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        result = results[0]

        if result.boxes.id is not None:
            track_ids = result.boxes.id.int().tolist()
            for box, track_id in zip(result.boxes, track_ids):
                class_id = int(box.cls[0])
                label = VEHICLE_CLASSES.get(class_id, "vehicle")
                confidence = float(box.conf[0])

                unique_ids_seen[label].add(track_id)

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    f"ID {track_id} {label} {confidence:.2f}",
                    (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2,
                )

        if frame_count % 30 == 0:
            summary = ", ".join(f"{len(ids)} {label}" for label, ids in unique_ids_seen.items())
            print(f"Frame {frame_count} -- unique vehicles so far: {summary}")

        if show_window:
            cv2.imshow("TrafficVision AI - Phase 2 (Tracking)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if show_window:
        cv2.destroyAllWindows()

    print("\n--- Final unique vehicle counts (each vehicle counted once) ---")
    total = 0
    for label, ids in unique_ids_seen.items():
        print(f"{label}: {len(ids)}")
        total += len(ids)
    print(f"total: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 vehicle tracking")
    parser.add_argument("--video", type=str, default="traffic.mp4", help="Path to input video file")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="YOLO model checkpoint to use")
    parser.add_argument("--conf", type=float, default=0.4, help="Confidence threshold (0-1)")
    parser.add_argument("--no-window", action="store_true", help="Disable live preview window")
    args = parser.parse_args()

    main(args.video, args.model, args.conf, show_window=not args.no_window)