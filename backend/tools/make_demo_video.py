"""
TrafficVision AI - Demo Video Generator / Downloader
-----------------------------------------------------
Generates or downloads a sample traffic video for testing the detection pipeline.
Saves to traffic.mp4 in the current directory or specified output path.
"""

import sys
import os
import urllib.request
import cv2
import numpy as np


SAMPLE_VIDEO_URL = "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/person-bicycle-car-detection.mp4"


def create_synthetic_traffic_video(output_path: str = "traffic.mp4", duration_sec: int = 10, fps: int = 30):
    """Generates a synthetic traffic video with lane markings and moving vehicles."""
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    total_frames = duration_sec * fps
    vehicles = [
        {"x": 180, "y": 50, "speed": 4, "color": (220, 100, 50), "w": 40, "h": 60, "name": "car1"},
        {"x": 260, "y": 80, "speed": 6, "color": (50, 200, 50), "w": 45, "h": 70, "name": "car2"},
        {"x": 380, "y": 400, "speed": -5, "color": (50, 50, 220), "w": 40, "h": 60, "name": "car3"},
        {"x": 460, "y": 350, "speed": -7, "color": (200, 200, 50), "w": 30, "h": 40, "name": "bike1"},
    ]

    for frame_idx in range(total_frames):
        frame = np.ones((height, width, 3), dtype=np.uint8) * 45  # dark asphalt

        # Road boundaries and lanes
        cv2.line(frame, (120, 0), (120, height), (255, 255, 255), 3)
        cv2.line(frame, (540, 0), (540, height), (255, 255, 255), 3)
        cv2.line(frame, (330, 0), (330, height), (255, 255, 0), 2)  # yellow median

        # Dashed lane dividers
        for y in range(0, height, 40):
            cv2.line(frame, (225, y), (225, y + 20), (255, 255, 255), 2)
            cv2.line(frame, (435, y), (435, y + 20), (255, 255, 255), 2)

        # Counting / Detection reference line (Y=240)
        cv2.line(frame, (120, 240), (540, 240), (0, 0, 255), 1)

        # Draw and move vehicles
        for v in vehicles:
            v["y"] += v["speed"]
            if v["y"] > height + 50:
                v["y"] = -50
            elif v["y"] < -50:
                v["y"] = height + 50

            vx, vy, vw, vh = int(v["x"]), int(v["y"]), v["w"], v["h"]
            cv2.rectangle(frame, (vx - vw // 2, vy - vh // 2), (vx + vw // 2, vy + vh // 2), v["color"], -1)
            cv2.rectangle(frame, (vx - vw // 2, vy - vh // 2), (vx + vw // 2, vy + vh // 2), (255, 255, 255), 1)

        out.write(frame)

    out.release()
    print(f"Generated synthetic demo video at {output_path} ({duration_sec}s @ {fps}fps)")


def download_or_create_demo_video(output_path: str = "traffic.mp4"):
    print(f"Downloading sample traffic video from {SAMPLE_VIDEO_URL}...")
    try:
        urllib.request.urlretrieve(SAMPLE_VIDEO_URL, output_path)
        print(f"Sample traffic video successfully downloaded to {output_path}")
    except Exception as e:
        print(f"Download failed ({e}). Falling back to creating synthetic video...")
        create_synthetic_traffic_video(output_path)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "traffic.mp4"
    download_or_create_demo_video(target)
