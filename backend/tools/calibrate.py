"""
TrafficVision AI - Camera Speed Homography Calibration Tool
------------------------------------------------------------
Allows selecting 4 reference points on a camera frame, entering real-world
metric distances, and generating the `calibration_points` configuration snippet
to paste into CAMERA_SOURCES in config.py.

Usage:
    python backend/tools/calibrate.py [--video traffic.mp4] [--width 7.0] [--length 20.0]
"""

import sys
import argparse
import cv2
import numpy as np


def run_calibration(video_path: str = "traffic.mp4", road_width_m: float = 7.0, road_len_m: float = 20.0):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file or stream '{video_path}'")
        sys.exit(1)

    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        print(f"Error: Could not read a valid frame from '{video_path}'")
        sys.exit(1)

    points = []
    clone = frame.copy()
    window_name = "Camera Calibration - Click 4 Points in Order (TL, TR, BR, BL) - Press 'q' when done"

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append([float(x), float(y)])
            idx = len(points)
            cv2.circle(clone, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(clone, f"P{idx}({x},{y})", (x + 8, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            cv2.imshow(window_name, clone)
            if len(points) == 4:
                # Draw quadrilateral
                pts_arr = np.array(points, np.int32).reshape((-1, 1, 2))
                cv2.polylines(clone, [pts_arr], isClosed=True, color=(0, 255, 0), thickness=2)
                cv2.imshow(window_name, clone)
                print("\n[+] 4 points captured!")

    # Check if GUI window can be shown
    try:
        cv2.imshow(window_name, clone)
        cv2.setMouseCallback(window_name, mouse_callback)
        print("Click 4 points on the road patch in order: Top-Left, Top-Right, Bottom-Right, Bottom-Left.")
        print("Press 'c' to clear points, 'q' or ESC to confirm and exit.")

        while True:
            key = cv2.waitKey(20) & 0xFF
            if key in (27, ord('q')):
                break
            elif key == ord('c'):
                points.clear()
                clone = frame.copy()
                cv2.imshow(window_name, clone)
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"Headless/GUI error ({e}). Using estimated frame coordinates.")
        h, w = frame.shape[:2]
        points = [
            [float(w * 0.3), float(h * 0.4)],
            [float(w * 0.7), float(h * 0.4)],
            [float(w * 0.85), float(h * 0.9)],
            [float(w * 0.15), float(h * 0.9)],
        ]

    if len(points) < 4:
        print("Calibration aborted: fewer than 4 points selected.")
        return

    # Real-world metric coordinates: Top-Left (0, L), Top-Right (W, L), Bottom-Right (W, 0), Bottom-Left (0, 0)
    world_points = [
        [0.0, float(road_len_m)],
        [float(road_width_m), float(road_len_m)],
        [float(road_width_m), 0.0],
        [0.0, 0.0],
    ]

    print("\n" + "=" * 60)
    print("CONFIG SNIPPET FOR config.py (CAMERA_SOURCES):")
    print("=" * 60)
    snippet = f"""    "calibration_points": {{
        "image_points": {points},
        "world_points": {world_points},
    }},"""
    print(snippet)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate camera speed homography")
    parser.add_argument("--video", default="traffic.mp4", help="Video path or camera stream")
    parser.add_argument("--width", type=float, default=7.0, help="Real-world patch width in meters (default 7.0m)")
    parser.add_argument("--length", type=float, default=20.0, help="Real-world patch length in meters (default 20.0m)")
    args = parser.parse_args()

    run_calibration(args.video, road_width_m=args.width, road_len_m=args.length)
