"""
Simple test client for the /ws/live WebSocket endpoint.
Connects, listens, and prints incoming detection messages.

Run this AFTER starting the server (uvicorn main:app --reload):
    python test_client.py
"""

import asyncio
import json

import websockets


async def listen():
    uri = "ws://127.0.0.1:8000/ws/live"
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}. Listening for messages (Ctrl+C to stop)...\n")
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            vehicle_summary = ", ".join(
                f"ID{v['id']}:{v['type']}" + (f"@{v['speed_kmh']}km/h" if v["speed_kmh"] else "")
                for v in data["vehicles"]
            )
            print(f"Frame {data['frame']} | counts={data['counts']} | vehicles=[{vehicle_summary}]")


if __name__ == "__main__":
    asyncio.run(listen())   