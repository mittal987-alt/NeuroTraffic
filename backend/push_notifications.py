"""
TrafficVision AI - Firebase push notification sender
------------------------------------------------------
Uses the Firebase Admin SDK to send push notifications from the
Python backend. This is separate from the Flutter-side FCM setup --
Flutter RECEIVES pushes, this module SENDS them.

Setup:
    pip install firebase-admin
    Place your downloaded service account JSON key at:
        backend/firebase-service-account.json
    (Firebase Console -> Project Settings -> Service Accounts ->
     Generate new private key)
"""

import os

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, messaging

import logging

load_dotenv()

# Initialize once safely when this module is imported
_firebase_initialized = False
try:
    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "firebase-service-account.json")
    if os.path.exists(cred_path):
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        _firebase_initialized = True
    else:
        logging.warning(f"Firebase service account file not found at {cred_path}. Push notifications disabled.")
except Exception as e:
    logging.warning(f"Failed to initialize Firebase Admin SDK: {e}")


def send_push_notification(token: str, title: str, body: str):
    """
    Sends a push notification to a single device.

    token: the FCM token for the target device (printed in the Flutter
           app's console on startup -- see main.dart's _setupNotifications)
    title: notification title, e.g. "Overspeed Alert"
    body:  notification body, e.g. "Car exceeded 80 km/h at Camera 1"
    """
    if not _firebase_initialized or not token or "PASTE_YOUR" in token:
        return False

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=token,
    )
    try:
        response = messaging.send(message)
        print(f"Push sent successfully: {response}")
        return True
    except Exception as e:
        print(f"Failed to send push: {e}")
        return False