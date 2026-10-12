"""
TrafficVision AI - Phase 1: Vehicle Detection
------------------------------------------------
Reads a video file, runs YOLO on every frame, draws boxes
around detected vehicles, and shows a live count in the console.

Run:
    python detect_vehicles.py --video traffic.mp4

Press 'q' to quit the preview window early.
"""

import argparse
from collections import Counter

import cv2
from ultralytics import YOLO

# COCO class IDs we care about for traffic (see model.names for the full list)
VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


def main(video_path: str, model_name: str, conf_threshold: float, show_window: bool):
    # Loads (and auto-downloads on first run) a pretrained YOLO model.
    # 'yolov8n.pt' is the small/fast variant -- good for getting started.
    # Swap to 'yolov8m.pt' or a YOLOv11 checkpoint later for better accuracy.
    model = YOLO(model_name)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")

    frame_count = 0
    total_class_counts = Counter()

    while True:
        ret, frame = cap.read()
        if not ret:
            break  # end of video

        frame_count += 1

        # Run detection on this single frame.
        # classes=list(VEHICLE_CLASSES) restricts YOLO to only report vehicle classes.
        results = model(frame, conf=conf_threshold, classes=list(VEHICLE_CLASSES.keys()), verbose=False)
        result = results[0]

        frame_class_counts = Counter()
        for box in result.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            label = VEHICLE_CLASSES.get(class_id, "vehicle")
            frame_class_counts[label] += 1

            # Draw box + label on the frame
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                frame,
                f"{label} {confidence:.2f}",
                (x1, max(y1 - 8, 0)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2,
            )

        total_class_counts.update(frame_class_counts)

        # Print a running summary every 30 frames so the console isn't spammed
        if frame_count % 30 == 0:
            summary = ", ".join(f"{v} {k}" for k, v in frame_class_counts.items()) or "none"
            print(f"Frame {frame_count}: {summary}")

        if show_window:
            cv2.imshow("TrafficVision AI - Phase 1", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if show_window:
        cv2.destroyAllWindows()

    print("\n--- Detection summary (sum across all frames, not unique vehicles) ---")
    for label, count in total_class_counts.items():
        print(f"{label}: {count}")
    print(
        "\nNote: this counts detections per frame, so the same car is counted "
        "many times as it moves through the video. Phase 2 (tracking) fixes "
        "this by giving each vehicle a stable ID."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1 vehicle detection")
    parser.add_argument("--video", type=str, default="traffic.mp4", help="Path to input video file")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="YOLO model checkpoint to use")
    parser.add_argument("--conf", type=float, default=0.4, help="Confidence threshold (0-1)")
    parser.add_argument("--no-window", action="store_true", help="Disable live preview window")
    args = parser.parse_args()

    main(args.video, args.model, args.conf, show_window=not args.no_window)