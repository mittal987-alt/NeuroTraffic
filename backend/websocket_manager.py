"""
TrafficVision AI - WebSocket connection manager + live frame buffer
------------------------------------------------
Tracks connected WebSocket clients and handles broadcasting JSON
messages to all of them. Also holds the latest JPEG frame per camera
(used by the MJPEG video preview endpoint) -- kept here so both the
WebSocket route and the MJPEG route can read/write without main.py
sitting in the middle.
"""

import json
from fastapi import WebSocket

# Tracks which WebSocket clients are currently connected
connected_clients: set[WebSocket] = set()

# Latest encoded JPEG bytes per camera, updated every frame by the
# detection pipeline. Read by the /stream/{camera_id} MJPEG endpoint.
latest_frame_jpeg: dict[str, bytes] = {}


async def broadcast(message: dict):
    """Send a JSON message to every currently connected WebSocket client."""
    if not connected_clients:
        return
    payload = json.dumps(message)
    disconnected = set()
    # Iterate over a copy to avoid "Set changed size during iteration" errors
    for client in list(connected_clients):
        try:
            await client.send_text(payload)
        except Exception:
            disconnected.add(client)
    connected_clients.difference_update(disconnected)