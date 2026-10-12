"""
TrafficVision AI - Face detection (capture, not recognition)
------------------------------------------------
Uses OpenCV's built-in Haar cascade to locate a face region within a
vehicle crop. This DETECTS a face is present and returns its crop --
it does NOT identify who the person is. No matching against any
database of known individuals happens here.
"""

import cv2
import logging

import os
try:
    _face_cascade = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
except (AttributeError, Exception) as e:
    logging.warning(f"Face cascade classifier not available: {e}")
    _face_cascade = None


def detect_face_crop(vehicle_crop):
    """Returns a cropped face image (numpy array) if found, else None."""
    if _face_cascade is None or _face_cascade.empty():
        return None
        
    gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
    if gray.shape[0] < 20 or gray.shape[1] < 20:
        return None
        
    try:
        faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20))
        if len(faces) == 0:
            return None
        x, y, w, h = faces[0]  # take the first/largest detected face
        return vehicle_crop[y:y + h, x:x + w]
    except (cv2.error, Exception):
        return None